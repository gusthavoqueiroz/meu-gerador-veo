import streamlit as st
import openai
import anthropic
import os

st.set_page_config(page_title="Gerador Veo 3 - Longa Duração", layout="wide")

st.title("🎬 Gerador de Prompts (Vídeos Longos)")
st.markdown("Configurado para processar vídeos de até 25 minutos.")

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
        
        st.info("⌛ Passo 1: Transcrevendo áudio completo (25 min)...")
        with open(temp_path, "rb") as f:
            transcript = client_oa.audio.transcriptions.create(
                model="whisper-1", 
                file=f,
                response_format="text"
            )

        # 2. Criação da Tabela com Claude Haiku
        st.info("⌛ Passo 2: Claude gerando a tabela detalhada...")
        client_cl = anthropic.Anthropic(api_key=cl_key)
        
        # PROMPT DE ALTO IMPACTO PARA VÍDEOS LONGOS
        prompt_final = f"""Você é um roteirista profissional. O áudio tem 25 minutos. 
        Abaixo está a transcrição. Gere o máximo de linhas que conseguir na tabela de 8 em 8 segundos, 
        começando de onde parou (ou do início se for a primeira vez).
        
        ESTILO: {estilo}
        TRANSCRICÃO: "{transcript}"
        
        REGRAS:
        1. Formate como tabela: Tempo | Texto Original | Prompt Veo 3 (em inglês).
        2. Se o texto for muito longo e você não conseguir terminar tudo, pare exatamente no final de uma linha da tabela.
        3. FOCO: Não resuma. Detalhe cada segmento de 8 segundos."""

        message = client_cl.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4096, # Limite máximo de escrita do Claude
            messages=[{"role": "user", "content": prompt_final}]
        )

        st.success("✅ Parte do Roteiro Gerada!")
        st.markdown(message.content[0].text)
        
        st.warning("⚠️ Nota: Devido ao tamanho do vídeo (25 min), o Claude pode ter parado antes do fim. Se faltou o final, você pode copiar o restante da transcrição e pedir para ele continuar.")

    except Exception as e:
        st.error(f"Erro: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
