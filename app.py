import streamlit as st
import openai
import anthropic
import os

st.set_page_config(page_title="Gerador Veo 3 - Estável", layout="wide")

st.title("🎬 Gerador de Prompts para Veo 3")

with st.sidebar:
    st.header("🔑 Configurações")
    oa_key = st.text_input("OpenAI Key", type="password")
    cl_key = st.text_input("Claude Key", type="password")
    estilo = st.text_input("Estilo Visual", value="Cinematic, 8k, realistic")

audio_file = st.file_uploader("Suba seu áudio (Máx 25MB)", type=['mp3', 'wav', 'm4a'])

if st.button("Gerar Prompts") and audio_file and oa_key and cl_key:
    temp_path = "temp_audio_file.mp3"
    try:
        # 1. Transcrição com OpenAI (Whisper)
        client_oa = openai.OpenAI(api_key=oa_key)
        with open(temp_path, "wb") as f:
            f.write(audio_file.getbuffer())
        
        st.info("⌛ OpenAI transcrevendo...")
        with open(temp_path, "rb") as f:
            transcript = client_oa.audio.transcriptions.create(
                model="whisper-1", 
                file=f,
                response_format="text" # Simplificado para evitar erro de objeto
            )

        # 2. Criação da Tabela com Claude
        st.info("⌛ Claude criando tabela...")
        client_cl = anthropic.Anthropic(api_key=cl_key)
        
        prompt_final = f"""Com base nesta transcrição de áudio:
        "{transcript}"
        
        Crie uma tabela de prompts para o gerador de vídeo VEO 3.
        REGRAS:
        1. Divida em blocos de 8 segundos baseados no fluxo do texto.
        2. Estilo visual: {estilo}.
        3. Prompts em INGLÊS.
        Formate como Tabela: Tempo | Texto Original | Prompt Veo 3"""

        message = client_cl.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt_final}]
        )

        st.success("✅ Tudo pronto!")
        st.markdown(message.content[0].text)

    except Exception as e:
        st.error(f"Erro: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
