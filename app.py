import streamlit as st
import openai
import anthropic
import os

st.set_page_config(page_title="Gerador Veo 3 - Versão Completa", layout="wide")

st.title("🎬 Gerador de Prompts para Veo 3")
st.markdown("Esta versão gera a tabela completa de todos os segmentos do seu áudio.")

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
        
        st.info("⌛ OpenAI transcrevendo áudio completo...")
        with open(temp_path, "rb") as f:
            transcript = client_oa.audio.transcriptions.create(
                model="whisper-1", 
                file=f,
                response_format="text"
            )

        # 2. Criação da Tabela com Claude Haiku (Modelo que funcionou na sua conta)
        st.info("⌛ Claude criando a tabela completa... Por favor, aguarde.")
        client_cl = anthropic.Anthropic(api_key=cl_key)
        
        # Prompt ajustado para não resumir e ir até o fim
        prompt_final = f"""Analise a transcrição COMPLETA abaixo e crie uma tabela
