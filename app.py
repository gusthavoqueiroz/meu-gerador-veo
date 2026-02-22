import streamlit as st
import openai
import anthropic
import os

st.set_page_config(page_title="Gerador Veo 3 - Versão Final", layout="wide")

st.title("🎬 Gerador de Prompts para Veo 3")
st.markdown("Geração de prompts completos a cada 8 segundos.")

with st.sidebar:
    st.header("🔑 Configurações")
    oa_key = st.text_input("OpenAI Key", type="password")
    cl_key = st.text_input("Claude Key", type="password")
    estilo = st.text_input("Estilo Visual", value="Cinematic, 8k, realistic, high detail")

audio_file = st.file_uploader("Suba seu áudio (Máx 25MB)", type=['mp3', 'wav', 'm4a'])

if st.button("Gerar Prompts") and audio_file and oa_key and cl_key:
    temp_path = "temp_audio_file.mp3"
    try:
        # 1. Transcrição com OpenAI
        client_oa = openai.OpenAI(api_key=oa_key)
        with open(temp_path, "wb") as f:
            f.write(audio_file.getbuffer())
        
        st.info("⌛ OpenAI transcrevendo...")
        with open(temp_path, "rb") as f:
            transcript = client_oa.audio.transcriptions.create(
                model="whisper-1", 
                file=f,
                response_format="text"
            )

        # 2. Criação da Tabela com Claude
        st.info("⌛ Claude criando tabela completa...")
        client_cl = anthropic.Anthropic(api_key=cl_key)
        
        # O bloco abaixo foi corrigido para evitar o erro de Syntax
        prompt_final = f"Analise a transcrição COMPLETA abaixo e crie uma tabela de prompts sem pular nenhuma frase: '{transcript}'. REGRAS: 1. Divida em blocos de EXATAMENTE 8 segundos até o FINAL. 2. Estilo visual: {estilo}. 3. Prompts em INGLÊS. Formato: Tempo | Texto Original | Prompt Veo 3"

        message = client_cl.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt_final}]
        )

        st.success("✅ Tabela Gerada!")
        st.markdown(message.content[0].text)

    except Exception as e:
        st.error(f"Erro: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
