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
            "claude-3-7-sonnet-latest"
        ],
        index=0
    )

    bloco_segundos = st.number_input(
        "Duração do bloco (segundos)",
        min_value=4,
        max_value=20,
        value=8
    )

    blocos_por_lote = st.number_input(
        "Blocos por lote",
        min_value=5,
        max_value=20,
        value=10
    )

    tentativas_por_lote = st.number_input(
        "Tentativas automáticas",
        min_value=1,
        max_value=5,
        value=3
    )

    max_tokens_saida = st.number_input(
        "Max tokens Claude",
        min_value=1000,
        max_value=8000,
        value=3500
    )

    temperatura = st.slider(
        "Criatividade",
        0.0,
        1.0,
        0.4
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

# -----------------------------
# FUNÇÕES
# -----------------------------

def safe_max_tokens(model, requested):

    limits = {
        "claude-3-haiku-20240307": 4096
    }

    default_limit = 4000
    limit = limits.get(model, default_limit)

    return min(requested, limit)


def format_seconds(seconds):

    seconds = int(seconds)
    m = seconds // 60
    s = seconds % 60

    return f"{m:02d}:{s:02d}"


def hash_file(uploaded_file):

    uploaded_file.seek(0)
    content = uploaded_file.read()
    uploaded_file.seek(0)

    return hashlib.md5(content).hexdigest()


def normalize_text(text):

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def create_blocks(segments, duration, block_size):

    total_blocks = math.ceil(duration / block_size)

    blocks = []

    for i in range(total_blocks):

        start = i * block_size
        end = min((i + 1) * block_size, duration)

        texts = []

        for seg in segments:

            if seg["end"] > start and seg["start"] < end:
                texts.append(seg["text"])

        text = normalize_text(" ".join(texts))

        if text == "":
            text = "[sem fala]"

        blocks.append(
            {
                "index": i + 1,
                "tempo": f"{format_seconds(start)}-{format_seconds(end)}",
                "texto": text
            }
        )

    return blocks


def parse_csv(text):

    rows = []

    text = text.replace("```csv", "")
    text = text.replace("```", "")

    reader = csv.reader(io.StringIO(text), delimiter=";")

    for row in reader:

        if len(row) < 4:
            continue

        if row[0].lower() == "index":
            continue

        try:

            rows.append(
                {
                    "index": int(row[0]),
                    "tempo": row[1],
                    "texto": row[2],
                    "prompt": ";".join(row[3:])
                }
            )

        except:
            pass

    return rows


def build_prompt(blocks, style):

    text = ""

    for b in blocks:

        text += f"{b['index']} | {b['tempo']} | {b['texto']}\n"

    prompt = f"""
You are an expert cinematic Veo 3 prompt writer.

GLOBAL STYLE:
{style}

Generate EXACTLY one prompt for each block.

Rules:

- one line per block
- English prompts
- no subtitles
- no text on screen
- no logos
- no watermark

Return CSV format:

index;tempo;texto_original;prompt_veo3

Blocks:
{text}
"""

    return prompt


def call_claude(client, model, prompt, tokens, temperature):

    tokens = safe_max_tokens(model, tokens)

    response = client.messages.create(
        model=model,
        max_tokens=tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}]
    )

    text = ""

    for part in response.content:

        if part.type == "text":
            text += part.text

    return text


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

    if file_hash in st.session_state.transcript_cache:

        data = st.session_state.transcript_cache[file_hash]

        segments = data["segments"]
        duration = data["duration"]

        st.info("Usando transcrição em cache.")

    else:

        with open("temp_audio", "wb") as f:
            f.write(audio_file.getbuffer())

        client_oa = openai.OpenAI(api_key=oa_key)

        st.info("Passo 1: Transcrevendo áudio...")

        with open("temp_audio", "rb") as f:

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
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text
                }
            )

        duration = transcript.duration

        st.session_state.transcript_cache[file_hash] = {
            "segments": segments,
            "duration": duration
        }

    blocks = create_blocks(segments, duration, bloco_segundos)

    st.success(f"Transcrição concluída. Duração: {format_seconds(duration)}")

    st.write("Total de blocos:", len(blocks))

    client_cl = anthropic.Anthropic(api_key=cl_key)

    total_lotes = math.ceil(len(blocks) / blocos_por_lote)

    st.info("Passo 2: Gerando prompts...")

    progress = st.progress(0)

    results = {}

    for lote in range(total_lotes):

        start = lote * blocos_por_lote
        end = start + blocos_por_lote

        batch = blocks[start:end]

        prompt = build_prompt(batch, estilo)

        for tentativa in range(tentativas_por_lote):

            try:

                raw = call_claude(
                    client_cl,
                    model_claude,
                    prompt,
                    max_tokens_saida,
                    temperatura
                )

                rows = parse_csv(raw)

                for r in rows:
                    results[r["index"]] = r

                break

            except Exception as e:

                time.sleep(2)

        progress.progress((lote + 1) / total_lotes)

    final = []

    for i in sorted(results.keys()):
        final.append(results[i])

    df = pd.DataFrame(final)

    st.session_state.final_df = df

# -----------------------------
# RESULTADO
# -----------------------------

if st.session_state.final_df is not None:

    df = st.session_state.final_df

    st.subheader("Resultado")

    st.dataframe(df)

    csv_data = df.to_csv(index=False, sep=";")

    st.download_button(
        "Baixar CSV",
        csv_data,
        file_name="prompts_veo3.csv"
    )

    excel = io.BytesIO()

    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    st.download_button(
        "Baixar XLSX",
        excel.getvalue(),
        file_name="prompts_veo3.xlsx"
    )
