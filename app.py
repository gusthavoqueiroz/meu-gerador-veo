import streamlit as st
import openai
import anthropic
import os

st.set_page_config(page_title="Gerador Veo 3 - Versão Sem Cortes", layout="wide")

st.title("🎬 Gerador de Prompts para Veo 3")
st.markdown("Configurado para gerar o roteiro COMPLETO sem resumir.")

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
        
        st.info("⌛ Passo 1: Transcrevendo áudio total...")
        with open(temp_path, "rb") as f:
            transcript = client_oa.audio.transcriptions.create(
                model="whisper-1", 
                file=f,
                response_format="text"
            )

        # 2. Criação da Tabela com Claude Haiku
        st.info("⌛ Passo 2: Claude gerando todos os prompts... (Isso pode demorar dependendo do tamanho do áudio)")
        client_cl = anthropic.Anthropic(api_key=cl_key)
        
        # PROMPT REFORÇADO PARA NÃO RESUMIR
        prompt_final = f"""Você é um roteirista de cinema detalhista. Sua tarefa é transformar a transcrição abaixo em uma tabela de prompts de 8 segundos para o VEO 3.

        TRANSCRICÃO PARA PROCESSAR: "{transcript}"

        INSTRUÇÕES CRÍTICAS:
        1. NÃO RESUMA. Se o áudio é longo, a tabela DEVE ser longa.
        2. Crie uma linha para cada 8 segundos de áudio, do segundo 0 até o ÚLTIMO segundo da transcrição.
        3. Se você parar antes de chegar ao fim do texto, você falhará na tarefa.
        4. Mantenha o estilo: {estilo}.
        5. Prompts em INGLÊS.

        FORMATO EXIGIDO:
        Tempo | Texto Original | Prompt Veo 3"""

        message = client_cl.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000, # Espaço para uma resposta bem longa
            messages=[{"role": "user", "content": prompt_final}]
        )

        st.success("✅ Tabela Completa Gerada!")
        st.markdown(message.content[0].text)

    except Exception as e:
        st.error(f"Erro: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
