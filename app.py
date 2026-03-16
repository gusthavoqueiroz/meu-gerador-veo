import streamlit as st
import openai
import anthropic
import os
import math
import csv
import io
import time
import re
import hashlib
import pandas as pd

st.set_page_config(page_title="Gerador Veo 3 Pro", layout="wide")

st.title("🎬 Gerador de Prompts Veo 3 Pro")
st.markdown("Gera prompts sincronizados em blocos de 8 segundos para vídeos longos.")

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("🔑 Configurações")

    oa_key = st.text_input("OpenAI Key", type="password")
    cl_key = st.text_input("Claude Key", type="password")

    estilo_preset = st.selectbox(
        "Preset de estilo",
        [
            "Histórico documental",
            "Bíblico cinematográfico",
            "Cinemático realista",
            "Personalizado"
        ],
        index=0
    )

    if estilo_preset == "Histórico documental":
        estilo = st.text_area(
            "Estilo Visual Global",
            value="Cinematic, ultra realistic, historical documentary style, dramatic lighting, realistic motion, film look, 8k detail, natural atmosphere, no text on screen"
        )
    elif estilo_preset == "Bíblico cinematográfico":
        estilo = st.text_area(
            "Estilo Visual Global",
            value="Cinematic, ultra realistic, biblical epic style, dramatic golden lighting, realistic motion, ancient world atmosphere, film look, high detail, no text on screen"
        )
    elif estilo_preset == "Cinemático realista":
        estilo = st.text_area(
            "Estilo Visual Global",
            value="Cinematic, ultra realistic, high detail, natural lighting, realistic motion, film look, no text on screen"
        )
    else:
        estilo = st.text_area(
            "Estilo Visual Global",
            value="Cinematic, ultra realistic, high detail, natural lighting, realistic motion, film look, no text on screen"
        )

    model_claude = st.selectbox(
        "Modelo Claude",
        [
            "claude-3-5-sonnet-latest",
            "claude-3-7-sonnet-latest",
            "claude-3-haiku-20240307"
        ],
        index=0
    )

    bloco_segundos = st.number_input(
        "Duração de cada bloco (segundos)",
        min_value=4,
        max_value=20,
        value=8,
        step=1
    )

    blocos_por_lote = st.number_input(
        "Blocos por lote",
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

    temperatura_prompts = st.slider(
        "Criatividade dos prompts",
        min_value=0.0,
        max_value=1.0,
        value=0.4,
        step=0.1
    )

audio_file = st.file_uploader(
    "Suba seu áudio",
    type=["mp3", "wav", "m4a"]
)

# =========================
# Session state
# =========================
if "final_df" not in st.session_state:
    st.session_state.final_df = None

if "raw_transcription" not in st.session_state:
    st.session_state.raw_transcription = None

if "blocks_data" not in st.session_state:
    st.session_state.blocks_data = None

if "transcript_cache" not in st.session_state:
    st.session_state.transcript_cache = {}

# =========================
# Helpers
# =========================
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

def hash_uploaded_file(uploaded_file) -> str:
    uploaded_file.seek(0)
    content = uploaded_file.read()
    uploaded_file.seek(0)
    return hashlib.md5(content).hexdigest()

def build_fixed_blocks(segments, total_duration=None, block_size=8):
    if not segments:
        return []

    if total_duration is None:
        total_duration = max(float(seg["end"]) for seg in segments)

    total_blocks = math.ceil(total_duration / block_size)
    blocks = []

    for i in range(total_blocks):
        start_t = i * block_size
        end_t = min((i + 1) * block_size, total_duration)

        texts = []
        for seg in segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            seg_text = normalize_text(seg["text"])

            if seg_end > start_t and seg_start < end_t and seg_text:
                texts.append(seg_text)

        joined_text = normalize_text(" ".join(texts))
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
    cleaned = response_text.strip()
    cleaned = re.sub(r"^```(?:csv|text)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    rows = []
    f = io.StringIO(cleaned)
    reader = csv.reader(f, delimiter=';')

    for row in reader:
        if not row:
            continue

        first = row[0].strip().lower()
        if first == "index":
            continue

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

def validate_batch_output(expected_blocks, parsed_rows):
    expected_indexes = {b["index"] for b in expected_blocks}
    valid_rows = []

    for row in parsed_rows:
        if row["index"] in expected_indexes and row["prompt_veo3"].strip():
            valid_rows.append(row)

    valid_indexes = {r["index"] for r in valid_rows}
    missing = sorted(expected_indexes - valid_indexes)

    dedup = {}
    for row in valid_rows:
        dedup[row["index"]] = row

    valid_rows = [dedup[k] for k in sorted(dedup.keys())]
    return valid_rows, missing

def build_prompt_for_batch(blocks_batch, estilo_visual):
    blocos_txt = []
    for b in blocks_batch:
        blocos_txt.append(f"{b['index']} | {b['tempo']} | {b['texto_original']}")

    joined_blocks = "\n".join(blocos_txt)

    prompt = f"""
You are an expert cinematic Veo 3 prompt writer.

Your task is to generate EXACTLY one English video prompt for EACH block below.

GLOBAL STYLE:
{estilo_visual}

RULES:
1. Return EXACTLY one line per block.
2. Do not skip any block.
3. Do not merge multiple blocks.
4. Keep the prompt in English.
5. Match the narration of that exact time interval.
6. No subtitles, no on-screen text, no logos, no watermarks.
7. Make the scene realistic, cinematic, visually clear, and suitable for AI video generation.
8. If the block says [sem fala], create a cinematic transition, atmosphere shot, environmental shot, or contextual visual.
9. Return ONLY CSV using semicolon separators.
10. Use this exact format:

index;tempo;texto_original;prompt_veo3

BLOCKS:
{joined_blocks}
""".strip()

    return prompt

def build_retry_prompt(missing_blocks, estilo_visual):
    blocos_txt = []
    for b in missing_blocks:
        blocos_txt.append(f"{b['index']} | {b['tempo']} | {b['texto_original']}")

    joined_blocks = "\n".join(blocos_txt)

    prompt = f"""
Generate EXACTLY one English Veo 3 video prompt for EACH block below.

GLOBAL STYLE:
{estilo_visual}

RULES:
1. Return EXACTLY one line per block.
2. Do not skip any block.
3. No extra commentary.
4. No subtitles, no on-screen text, no logos, no watermarks.
5. Return ONLY CSV using semicolon separators.
6. Use this exact format:

index;tempo;texto_original;prompt_veo3

BLOCKS:
{joined_blocks}
""".strip()

    return prompt

def call_claude(client_cl, prompt, model_name, max_tokens, temperature):
    response = client_cl.messages.create(
        model=model_name,
        max_tokens=int(max_tokens),
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}]
    )

    parts = []
    for item in response.content:
        if getattr(item, "type", None) == "text":
            parts.append(item.text)

    return "\n".join(parts).strip()

def dataframe_to_csv_string(df: pd.DataFrame) -> str:
    output = io.StringIO()
    df.to_csv(output, sep=";", index=False)
    return output.getvalue()

def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="prompts")
    return output.getvalue()

# =========================
# Main action
# =========================
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
        file_hash = hash_uploaded_file(audio_file)

        if file_hash in st.session_state.transcript_cache:
            cached = st.session_state.transcript_cache[file_hash]
            segments = cached["segments"]
            total_duration = cached["duration"]
            full_text = cached["text"]
            st.info("♻️ Usando transcrição em cache.")
        else:
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

            segments = []
            for seg in transcript.segments:
                segments.append({
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": seg.text
                })

            total_duration = float(getattr(transcript, "duration", 0) or 0)
            full_text = getattr(transcript, "text", "")

            st.session_state.transcript_cache[file_hash] = {
                "segments": segments,
                "duration": total_duration,
                "text": full_text
            }

        blocks = build_fixed_blocks(
            segments=segments,
            total_duration=total_duration,
            block_size=bloco_segundos
        )

        st.session_state.raw_transcription = full_text
        st.session_state.blocks_data = blocks

        st.success(f"✅ Transcrição concluída. Duração detectada: {format_seconds(total_duration)}")
        st.write(f"Total de blocos: **{len(blocks)}**")

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

            for attempt in range(1, int(tentativas_por_lote) + 1):
                if attempt == 1:
                    prompt = build_prompt_for_batch(batch, estilo)
                    raw_text = call_claude(
                        client_cl=client_cl,
                        prompt=prompt,
                        model_name=model_claude,
                        max_tokens=max_tokens_saida,
                        temperature=temperatura_prompts
                    )
                    parsed_rows = parse_csv_response(raw_text)
                else:
                    missing_blocks = [b for b in batch if b["index"] in missing]
                    if not missing_blocks:
                        break

                    retry_prompt = build_retry_prompt(missing_blocks, estilo)
                    retry_text = call_claude(
                        client_cl=client_cl,
                        prompt=retry_prompt,
                        model_name=model_claude,
                        max_tokens=max_tokens_saida,
                        temperature=temperatura_prompts
                    )
                    retry_rows = parse_csv_response(retry_text)
                    parsed_rows.extend(retry_rows)

                valid_rows, missing = validate_batch_output(batch, parsed_rows)
                if not missing:
                    parsed_rows = valid_rows
                    break

                time.sleep(1)

            valid_rows, missing = validate_batch_output(batch, parsed_rows)

            if missing:
                missing_blocks = [b for b in batch if b["index"] in missing]
                for mb in missing_blocks:
                    fallback_prompt = (
                        f"Cinematic realistic scene representing the narration at this moment, "
                        f"showing the context of '{mb['texto_original']}', filmic composition, "
                        f"realistic motion, high detail, natural atmosphere, no on-screen text, no logos, no watermark."
                    )
                    valid_rows.append({
                        "index": mb["index"],
                        "tempo": mb["tempo"],
                        "texto_original": mb["texto_original"],
                        "prompt_veo3": fallback_prompt
                    })

            for row in valid_rows:
                all_rows_map[row["index"]] = row

            progress_bar.progress((lote_idx + 1) / total_lotes)

        final_rows = [all_rows_map[k] for k in sorted(all_rows_map.keys())]
        final_df = pd.DataFrame(final_rows)

        st.session_state.final_df = final_df
        st.success("✅ Processo concluído com sucesso.")

    except Exception as e:
        st.error(f"Erro: {e}")

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# =========================
# Results
# =========================
if st.session_state.final_df is not None:
    df = st.session_state.final_df

    st.subheader("Resultado final")
    st.dataframe(df, use_container_width=True, height=500)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Total de prompts", len(df))

    with c2:
        if st.session_state.blocks_data:
            st.metric("Total de blocos", len(st.session_state.blocks_data))

    with c3:
        cobertura = 0
        if st.session_state.blocks_data:
            total_blocos = len(st.session_state.blocks_data)
            if total_blocos > 0:
                cobertura = round((len(df) / total_blocos) * 100, 1)
        st.metric("Cobertura", f"{cobertura}%")

    csv_data = dataframe_to_csv_string(df)
    excel_data = dataframe_to_excel_bytes(df)

    st.download_button(
        label="📥 Baixar CSV",
        data=csv_data,
        file_name="prompts_veo3_8s.csv",
        mime="text/csv"
    )

    st.download_button(
        label="📥 Baixar XLSX",
        data=excel_data,
        file_name="prompts_veo3_8s.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
