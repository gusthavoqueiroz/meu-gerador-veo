import streamlit as st
import openai
import anthropic
import os
import math
import csv
import io
import time
import re
import pandas as pd

st.set_page_config(page_title="Gerador Veo 3 - 30 Min", layout="wide")

st.title("🎬 Gerador de Prompts Veo 3")
st.markdown("Gera prompts sincronizados em blocos de 8 segundos para vídeos longos.")

with st.sidebar:
    st.header("🔑 Configurações")
    oa_key = st.text_input("OpenAI Key", type="password")
    cl_key = st.text_input("Claude Key", type="password")

    estilo = st.text_area(
        "Estilo Visual Global",
        value="Cinematic, ultra realistic, high detail, natural lighting, realistic motion, film look, no text on screen"
    )

    model_claude = st.text_input(
        "Modelo Claude",
        value="claude-sonnet-4-5"
    )

    blocos_por_lote = st.number_input(
        "Blocos de 8s por lote",
        min_value=5,
        max_value=30,
        value=15,
        step=1
    )

    tentativas_por_lote = st.number_input(
        "Tentativas automáticas por lote",
        min_value=1,
        max_value=5,
        value=3,
        step=1
    )

    max_tokens_saida = st.number_input(
        "Max tokens da resposta do Claude",
        min_value=1000,
        max_value=12000,
        value=5000,
        step=500
    )

audio_file = st.file_uploader(
    "Suba seu áudio",
    type=["mp3", "wav", "m4a"]
)

# ---------------------------
# Utilidades
# ---------------------------

def format_seconds(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text

def build_8s_blocks(segments, total_duration=None, block_size=8):
    """
    Cria blocos fixos de 8 segundos a partir dos segmentos transcritos.
    """
    if not segments:
        return []

    if total_duration is None:
        total_duration = max(float(seg["end"]) for seg in segments)

    total_blocks = math.ceil(total_duration / block_size)
    blocks = []

    for i in range(total_blocks):
        start_t = i * block_size
        end_t = min((i + 1) * block_size, total_duration)

        textos = []
        for seg in segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            seg_text = normalize_text(seg["text"])

            # Interseção do segmento com o bloco
            if seg_end > start_t and seg_start < end_t and seg_text:
                textos.append(seg_text)

        joined_text = normalize_text(" ".join(textos))
        if not joined_text:
            joined_text = "[sem fala]"

        blocks.append({
            "index": i + 1,
            "start": round(start_t, 2),
            "end": round(end_t, 2),
            "tempo": f"{format_seconds(start_t)}-{format_seconds(end_t)}",
            "texto_original": joined_text
        })

    return blocks

def parse_csv_response(response_text: str):
    """
    Tenta interpretar o retorno do Claude no formato:
    index;tempo;texto_original;prompt_veo3
    """
    cleaned = response_text.strip()

    # Remove fences de markdown se vierem
    cleaned = re.sub(r"^```(?:csv|text)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    rows = []
    f = io.StringIO(cleaned)
    reader = csv.reader(f, delimiter=';')

    for row in reader:
        if not row:
            continue

        # Ignora cabeçalho
        first = row[0].strip().lower()
        if first == "index":
            continue

        # Junta colunas excedentes no prompt final
        if len(row) >= 4:
            idx = row[0].strip()
            tempo = row[1].strip()
            texto_original = row[2].strip()
            prompt_veo3 = ";".join(row[3:]).strip()

            if idx.isdigit():
                rows.append({
                    "index": int(idx),
                    "tempo": tempo,
                    "texto_original": texto_original,
                    "prompt_veo3": prompt_veo3
                })

    return rows

def build_prompt_for_batch(blocks_batch, estilo_visual):
    blocos_txt = []
    for b in blocks_batch:
        blocos_txt.append(
            f"{b['index']} | {b['tempo']} | {b['texto_original']}"
        )

    joined_blocks = "\n".join(blocos_txt)

    prompt = f"""
You are an expert cinematic prompt writer for Veo 3.

Your task is to generate EXACTLY one video prompt in English for EACH block below.

GLOBAL VISUAL STYLE:
{estilo_visual}

IMPORTANT RULES:
1. Return EXACTLY one line per block.
2. Do not skip any block.
3. Do not merge multiple blocks into one line.
4. The prompt must be in English.
5. The original text may remain in the source language.
6. The prompt must visually match the narration in that exact time interval.
7. No subtitles, no on-screen text, no captions, no logos, no watermarks.
8. Focus on cinematic, realistic, visually clear, filmable scenes.
9. If the block has very little speech or says [sem fala], still create a relevant visual prompt.
10. Keep each prompt detailed but concise enough to fit safely in one CSV row.
11. Return ONLY valid CSV with semicolon separator in this exact format:

index;tempo;texto_original;prompt_veo3

BLOCKS:
{joined_blocks}
""".strip()

    return prompt

def call_claude_batch(client_cl, blocks_batch, estilo_visual, model_name, max_tokens):
    prompt = build_prompt_for_batch(blocks_batch, estilo_visual)

    response = client_cl.messages.create(
        model=model_name,
        max_tokens=int(max_tokens),
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Junta blocos de texto se vier mais de um
    parts = []
    for item in response.content:
        if getattr(item, "type", None) == "text":
            parts.append(item.text)

    return "\n".join(parts).strip()

def validate_batch_output(expected_blocks, parsed_rows):
    expected_indexes = {b["index"] for b in expected_blocks}
    returned_indexes = {r["index"] for r in parsed_rows}

    missing = sorted(expected_indexes - returned_indexes)

    # Também filtra linhas vazias ou ruins
    valid_rows = []
    for row in parsed_rows:
        if row["index"] in expected_indexes and row["prompt_veo3"].strip():
            valid_rows.append(row)

    valid_indexes = {r["index"] for r in valid_rows}
    missing = sorted(expected_indexes - valid_indexes)

    return valid_rows, missing

def generate_missing_only_prompt(missing_blocks, estilo_visual):
    blocos_txt = []
    for b in missing_blocks:
        blocos_txt.append(f"{b['index']} | {b['tempo']} | {b['texto_original']}")

    joined_blocks = "\n".join(blocos_txt)

    prompt = f"""
Generate EXACTLY one Veo 3 video prompt in English for EACH missing block below.

GLOBAL VISUAL STYLE:
{estilo_visual}

RULES:
1. Return EXACTLY one line per block.
2. Do not skip any block.
3. Do not add commentary.
4. No subtitles, no on-screen text, no logos, no watermarks.
5. Return ONLY CSV with semicolon separator in this exact format:

index;tempo;texto_original;prompt_veo3

MISSING BLOCKS:
{joined_blocks}
""".strip()

    return prompt

def retry_missing_blocks(client_cl, missing_blocks, estilo_visual, model_name, max_tokens):
    prompt = generate_missing_only_prompt(missing_blocks, estilo_visual)

    response = client_cl.messages.create(
        model=model_name,
        max_tokens=int(max_tokens),
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    parts = []
    for item in response.content:
        if getattr(item, "type", None) == "text":
            parts.append(item.text)

    text = "\n".join(parts).strip()
    return parse_csv_response(text)

def dataframe_to_csv_string(df: pd.DataFrame) -> str:
    output = io.StringIO()
    df.to_csv(output, sep=";", index=False)
    return output.getvalue()

# ---------------------------
# Estado
# ---------------------------

if "final_df" not in st.session_state:
    st.session_state.final_df = None

if "raw_transcription" not in st.session_state:
    st.session_state.raw_transcription = None

# ---------------------------
# Execução principal
# ---------------------------

if st.button("Gerar Prompts"):
    if not audio_file:
        st.error("Envie um áudio.")
        st.stop()
    if not oa_key:
        st.error("Informe a OpenAI Key.")
        st.stop()
    if not cl_key:
        st.error("Informe a Claude Key.")
        st.stop()

    temp_path = f"temp_{audio_file.name}"

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_file.getbuffer())

        st.info("⌛ Passo 1: Transcrevendo áudio com timestamps...")
        client_oa = openai.OpenAI(api_key=oa_key)

        with open(temp_path, "rb") as f:
            transcript = client_oa.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

        # A API retorna segmentos com start/end/text nesse formato verbose_json
        segments = []
        for seg in transcript.segments:
            segments.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text
            })

        total_duration = float(getattr(transcript, "duration", 0) or 0)
        blocks = build_8s_blocks(segments, total_duration=total_duration, block_size=8)

        st.session_state.raw_transcription = getattr(transcript, "text", "")

        st.success(f"✅ Transcrição concluída. Duração detectada: {format_seconds(total_duration)}")
        st.write(f"Total de blocos de 8 segundos: **{len(blocks)}**")

        st.info("⌛ Passo 2: Gerando prompts em lotes...")
        client_cl = anthropic.Anthropic(api_key=cl_key)

        total_lotes = math.ceil(len(blocks) / blocos_por_lote)
        progress_bar = st.progress(0)
        status_box = st.empty()

        all_rows_map = {}

        for lote_idx in range(total_lotes):
            start_idx = lote_idx * blocos_por_lote
            end_idx = start_idx + blocos_por_lote
            batch = blocks[start_idx:end_idx]

            status_box.info(f"Processando lote {lote_idx + 1}/{total_lotes}...")

            parsed_rows = []
            missing = [b["index"] for b in batch]

            # Tentativa principal + retries
            for attempt in range(1, int(tentativas_por_lote) + 1):
                if attempt == 1:
                    raw_text = call_claude_batch(
                        client_cl=client_cl,
                        blocks_batch=batch,
                        estilo_visual=estilo,
                        model_name=model_claude,
                        max_tokens=max_tokens_saida
                    )
                    parsed_rows = parse_csv_response(raw_text)
                else:
                    missing_blocks = [b for b in batch if b["index"] in missing]
                    if not missing_blocks:
                        break

                    retry_rows = retry_missing_blocks(
                        client_cl=client_cl,
                        missing_blocks=missing_blocks,
                        estilo_visual=estilo,
                        model_name=model_claude,
                        max_tokens=max_tokens_saida
                    )
                    parsed_rows.extend(retry_rows)

                valid_rows, missing = validate_batch_output(batch, parsed_rows)

                if not missing:
                    parsed_rows = valid_rows
                    break

                time.sleep(1)

            valid_rows, missing = validate_batch_output(batch, parsed_rows)

            # Se ainda faltar, cria fallback simples para não perder sincronização
            if missing:
                missing_blocks = [b for b in batch if b["index"] in missing]
                for mb in missing_blocks:
                    fallback_prompt = (
                        f"Cinematic realistic scene visually representing the narration for this moment, "
                        f"matching the context '{mb['texto_original']}', natural motion, filmic composition, "
                        f"high detail, no on-screen text, no logos, no watermark."
                    )
                    valid_rows.append({
                        "index": mb["index"],
                        "tempo": mb["tempo"],
                        "texto_original": mb["texto_original"],
                        "prompt_veo3": fallback_prompt
                    })

            # Salva por índice para evitar duplicados
            for row in valid_rows:
                all_rows_map[row["index"]] = row

            progress_bar.progress((lote_idx + 1) / total_lotes)

        # Ordena tudo
        final_rows = [all_rows_map[k] for k in sorted(all_rows_map.keys())]
        final_df = pd.DataFrame(final_rows)

        st.session_state.final_df = final_df

        st.success("✅ Processo concluído com sucesso.")

    except Exception as e:
        st.error(f"Erro: {e}")

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ---------------------------
# Exibição dos resultados
# ---------------------------

if st.session_state.final_df is not None:
    df = st.session_state.final_df

    st.subheader("Resultado final")
    st.dataframe(df, use_container_width=True, height=500)

    csv_data = dataframe_to_csv_string(df)

    st.download_button(
        label="📥 Baixar CSV",
        data=csv_data,
        file_name="prompts_veo3_8s.csv",
        mime="text/csv"
    )

    txt_output = []
    for _, row in df.iterrows():
        txt_output.append(
            f"{row['index']} | {row['tempo']} | {row['texto_original']} | {row['prompt_veo3']}"
        )

    st.download_button(
        label="📥 Baixar TXT",
        data="\n".join(txt_output),
        file_name="prompts_veo3_8s.txt",
        mime="text/plain"
    )

    with st.expander("Ver CSV bruto"):
        st.text_area("CSV", csv_data, height=300)

if st.session_state.raw_transcription:
    with st.expander("Ver transcrição completa"):
        st.text_area("Transcrição", st.session_state.raw_transcription, height=300)
