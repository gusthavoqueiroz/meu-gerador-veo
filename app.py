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
st.markdown("Gera prompts sincronizados em blocos de tempo para vídeos longos.")

# -----------------------------
# CONFIGURAÇÕES SIDEBAR
# -----------------------------
with st.sidebar:
    st.header("🔑 Configurações")

    oa_key = st.text_input("OpenAI Key", type="password")
    cl_key = st.text_input("Claude Key", type="password")

    estilo = st.text_area(
        "Estilo Visual Global",
        value="Cinematic, ultra realistic, historical documentary style, dramatic lighting, realistic motion, film look, 8k detail, natural atmosphere, no text on screen"
    )

    model_claude = st.selectbox(
        "Modelo Claude",
        [
            "claude-3-haiku-20240307",
            "claude-3-7-sonnet-latest",
        ],
        index=0
    )

    bloco_segundos = st.number_input(
        "Duração do bloco (segundos)",
        min_value=4,
        max_value=20,
        value=8,
        step=1
    )

    blocos_por_lote = st.number_input(
        "Blocos por lote",
        min_value=5,
        max_value=20,
        value=10,
        step=1
    )

    tentativas_por_lote = st.number_input(
        "Tentativas automáticas",
        min_value=1,
        max_value=5,
        value=3,
        step=1
    )

    max_tokens_saida = st.number_input(
        "Max tokens Claude",
        min_value=1000,
        max_value=8000,
        value=3500,
        step=100
    )

    temperatura = st.slider(
        "Criatividade",
        min_value=0.0,
        max_value=1.0,
        value=0.4,
        step=0.1
    )

audio_file = st.file_uploader(
    "Suba seu áudio",
    type=["mp3", "wav", "m4a"]
)

# -----------------------------
# SESSION STATE
# -----------------------------
if "final_df" not in st.session_state:
    st.session_state.final_df = None

if "transcript_cache" not in st.session_state:
    st.session_state.transcript_cache = {}

if "raw_transcription" not in st.session_state:
    st.session_state.raw_transcription = ""

# -----------------------------
# FUNÇÕES AUXILIARES
# -----------------------------
def safe_max_tokens(model_name: str, requested: int) -> int:
    limits = {
        "claude-3-haiku-20240307": 4096,
    }
    default_limit = 4000
    model_limit = limits.get(model_name, default_limit)
    return min(int(requested), model_limit)


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def hash_file(uploaded_file) -> str:
    uploaded_file.seek(0)
    content = uploaded_file.read()
    uploaded_file.seek(0)
    return hashlib.md5(content).hexdigest()


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def create_blocks(segments, duration: float, block_size: int):
    total_blocks = math.ceil(duration / block_size)
    blocks = []

    for i in range(total_blocks):
        start = i * block_size
        end = min((i + 1) * block_size, duration)

        texts = []
        for seg in segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            if seg_end > start and seg_start < end:
                texts.append(seg["text"])

        joined_text = normalize_text(" ".join(texts))
        if not joined_text:
            joined_text = "[sem fala]"

        blocks.append(
            {
                "index": i + 1,
                "tempo": f"{format_seconds(start)}-{format_seconds(end)}",
                "texto_original": joined_text,
            }
        )

    return blocks


def parse_csv(text: str):
    rows = []

    cleaned = text.strip()
    cleaned = cleaned.replace("```csv", "").replace("```", "")
    cleaned = cleaned.strip()

    reader = csv.reader(io.StringIO(cleaned), delimiter=";")

    for row in reader:
        if not row or len(row) < 4:
            continue

        if row[0].strip().lower() == "index":
            continue

        try:
            idx = int(row[0].strip())
            tempo = row[1].strip()
            texto_original = row[2].strip()
            prompt_veo3 = ";".join(row[3:]).strip()

            if prompt_veo3:
                rows.append(
                    {
                        "index": idx,
                        "tempo": tempo,
                        "texto_original": texto_original,
                        "prompt_veo3": prompt_veo3,
                    }
                )
        except Exception:
            pass

    return rows


def build_prompt(blocks, style: str) -> str:
    text = ""
    for b in blocks:
        text += f"{b['index']} | {b['tempo']} | {b['texto_original']}\n"

    prompt = f"""
You are an expert cinematic Veo 3 prompt writer.

GLOBAL STYLE:
{style}

Generate EXACTLY one prompt for each block.

Rules:
- one line per block
- English prompts
- the prompt must visually match the narration of that exact block
- no subtitles
- no text on screen
- no logos
- no watermark
- if the block says [sem fala], generate a cinematic environmental or transition shot
- return ONLY CSV

Use exactly this format:
index;tempo;texto_original;prompt_veo3

Blocks:
{text}
"""
    return prompt.strip()


def call_claude(client, model: str, prompt: str, tokens: int, temperature: float) -> str:
    safe_tokens = safe_max_tokens(model, tokens)

    response = client.messages.create(
        model=model,
        max_tokens=safe_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for part in response.content:
        if getattr(part, "type", None) == "text":
            text += part.text

    return text


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8")


# -----------------------------
# BOTÃO PRINCIPAL
# -----------------------------
if st.button("Gerar Prompts"):
    if not audio_file:
        st.error("Envie um áudio.")
        st.stop()

    if not oa_key:
        st.error("Informe a OpenAI key.")
        st.stop()

    if not cl_key:
        st.error("Informe a Claude key.")
        st.stop()

    file_hash = hash_file(audio_file)

    try:
        if file_hash in st.session_state.transcript_cache:
            cached = st.session_state.transcript_cache[file_hash]
            segments = cached["segments"]
            duration = cached["duration"]
            full_text = cached["text"]
            st.info("♻️ Usando transcrição em cache.")
        else:
            temp_filename = f"temp_{audio_file.name}"

            with open(temp_filename, "wb") as f:
                f.write(audio_file.getbuffer())

            st.info("⏳ Passo 1: Transcrevendo áudio com timestamps...")
            client_oa = openai.OpenAI(api_key=oa_key)

            with open(temp_filename, "rb") as f:
                transcript = client_oa.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            segments = []
            for seg in transcript.segments:
                segments.append(
                    {
                        "start": float(seg.start),
                        "end": float(seg.end),
                        "text": seg.text,
                    }
                )

            duration = float(getattr(transcript, "duration", 0) or 0)
            full_text = getattr(transcript, "text", "")

            st.session_state.transcript_cache[file_hash] = {
                "segments": segments,
                "duration": duration,
                "text": full_text,
            }

            if os.path.exists(temp_filename):
                os.remove(temp_filename)

        st.session_state.raw_transcription = full_text

        blocks = create_blocks(segments, duration, int(bloco_segundos))

        st.success(f"✅ Transcrição concluída. Duração: {format_seconds(duration)}")
        st.write(f"Total de blocos: **{len(blocks)}**")

        st.info("⏳ Passo 2: Gerando prompts em lotes...")
        client_cl = anthropic.Anthropic(api_key=cl_key)

        total_lotes = math.ceil(len(blocks) / int(blocos_por_lote))
        progress = st.progress(0)
        status_box = st.empty()

        results = {}

        for lote in range(total_lotes):
            start_idx = lote * int(blocos_por_lote)
            end_idx = start_idx + int(blocos_por_lote)
            batch = blocks[start_idx:end_idx]

            status_box.info(f"Processando lote {lote + 1}/{total_lotes}...")

            prompt = build_prompt(batch, estilo)
            batch_ok = False

            for tentativa in range(int(tentativas_por_lote)):
                try:
                    raw = call_claude(
                        client_cl,
                        model_claude,
                        prompt,
                        int(max_tokens_saida),
                        float(temperatura)
                    )

                    rows = parse_csv(raw)

                    for r in rows:
                        results[r["index"]] = r

                    if rows:
                        batch_ok = True
                        break

                except Exception:
                    time.sleep(2)

            if not batch_ok:
                for b in batch:
                    if b["index"] not in results:
                        results[b["index"]] = {
                            "index": b["index"],
                            "tempo": b["tempo"],
                            "texto_original": b["texto_original"],
                            "prompt_veo3": (
                                f"Cinematic ultra-realistic historical documentary style scene representing "
                                f"the narration context '{b['texto_original']}', dramatic lighting, realistic motion, "
                                f"natural atmosphere, film look, no text on screen, no logos, no watermark."
                            )
                        }

            progress.progress((lote + 1) / total_lotes)

        final_rows = [results[i] for i in sorted(results.keys())]
        df = pd.DataFrame(final_rows)
        st.session_state.final_df = df

        st.success("✅ Processo concluído com sucesso.")

    except Exception as e:
        st.error(f"Erro: {e}")

# -----------------------------
# RESULTADO
# -----------------------------
if st.session_state.final_df is not None:
    df = st.session_state.final_df

    st.subheader("Resultado")
    st.dataframe(df, use_container_width=True, height=500)

    csv_data = dataframe_to_csv_bytes(df)

    st.download_button(
        "Baixar CSV",
        data=csv_data,
        file_name="prompts_veo3.csv",
        mime="text/csv"
    )

    try:
        import openpyxl  # noqa: F401

        excel = io.BytesIO()
        with pd.ExcelWriter(excel, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="prompts")

        st.download_button(
            "Baixar XLSX",
            data=excel.getvalue(),
            file_name="prompts_veo3.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except ModuleNotFoundError:
        st.warning("openpyxl não está instalado no ambiente. O download em XLSX foi desativado, mas o CSV está disponível normalmente.")

    with st.expander("Ver CSV bruto"):
        st.text_area("CSV", df.to_csv(index=False, sep=";"), height=300)

if st.session_state.raw_transcription:
    with st.expander("Ver transcrição completa"):
        st.text_area("Transcrição", st.session_state.raw_transcription, height=300)
