import streamlit as st
import openai
import anthropic
import os

st.set_page_config(page_title="Gerador Veo 3 - Final", layout="wide")

st.title("🎬 Gerador de Prompts para Veo 3")

with st.sidebar:
    st.header("🔑 Configurações")
    oa_key = st.text_input("OpenAI Key", type="password")
    cl_key = st.text_input("Claude Key", type="password")
    estilo = st.text_input("Estilo Visual", value="Cinematic, 8k, realistic")

audio_file = st.file_uploader("Suba seu áudio (Máx 25MB)", type=['mp3', 'wav', 'm4a'])

if st.button("Gerar Prompts") and audio_file and oa_key and cl_key:
    try:
        client_oa = openai.OpenAI(api_key=oa_key)
        
        with open("temp_audio.mp3", "wb") as f:
            f.write(audio_file.getbuffer())
        
        st.info("⌛ Transcrevendo áudio...")
        
        with open("temp_audio.mp3", "rb") as f:
            transcript = client_oa.audio.transcriptions.create(
                model="whisper-1", 
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

        st.info("⌛ Claude criando prompts de 8 segundos...")
        client_cl = anthropic.Anthropic(api_key=cl_key)
        
        # Acesso via objeto (.start) corrigido
        texto_com_tempo = ""
        for s in transcript.segments:
            texto_com_tempo += f"[{s.start}-{s.end}s]: {s.text}\n"

        prompt_final = f"""Com base nesta transcrição:
        {texto_com_tempo}
        
        Crie uma tabela de prompts para o gerador de vídeo VEO 3.
        REGRAS:
        1. Divida em blocos de EXATAMENTE 8 segundos (0-8s, 8-16s, etc).
        2. Estilo visual: {estilo}.
        3. Prompts em INGLÊS focando em movimento de câmera e iluminação.
        Formate como Tabela: Tempo | Texto Original | Prompt Veo 3"""

        # MODELO ATUALIZADO PARA O MAIS RECENTE
        message = client_cl.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt_final}]
        )

        st.success("✅ Pronto!")
        st.markdown(message.content[0].text)
        
        os.remove("temp_audio.mp3")

    except Exception as e:
        st.error(f"Erro: {e}")
        if os.path.exists("temp_audio.mp3"):
            os.remove("temp_audio.mp3")
