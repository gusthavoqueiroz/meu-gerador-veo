import streamlit as st
import anthropic
import base64
import os

st.set_page_config(page_title="Gerador Veo 3 - Versão Claude", layout="wide")

st.title("🎬 Gerador de Prompts para Veo 3")
st.markdown("Esta versão usa o Claude 3.5 Sonnet para ouvir seu áudio diretamente.")

with st.sidebar:
    st.header("🔑 Configuração")
    cl_key = st.text_input("Claude API Key", type="password")
    estilo = st.text_input("Estilo Visual", value="Cinematic, 8k, realistic, high detail")

# Claude aceita até 100MB
audio_file = st.file_uploader("Suba seu áudio (MP3, WAV, M4A)", type=['mp3', 'wav', 'm4a'])

if st.button("Gerar Prompts") and audio_file and cl_key:
    try:
        client = anthropic.Anthropic(api_key=cl_key)
        
        st.info("⌛ O Claude está ouvindo e processando seu áudio... Isso pode levar um minuto.")
        
        # Converte o áudio para base64 para enviar ao Claude
        audio_data = base64.b64encode(audio_file.read()).decode("utf-8")
        audio_type = f"audio/{audio_file.name.split('.')[-1]}"
        if "m4a" in audio_type: audio_type = "audio/mp4" # Ajuste para m4a

        prompt = f"""Analise este áudio e crie uma tabela de prompts para o gerador de vídeo VEO 3.
        REGRAS:
        1. Divida o conteúdo em blocos de EXATAMENTE 8 segundos (0-8s, 8-16s, 16-24s, etc).
        2. Para cada bloco, descreva uma cena visual baseada no que é dito.
        3. Estilo visual: {estilo}.
        4. Os prompts devem estar em INGLÊS.
        Formate como uma Tabela: Tempo | Descrição do Áudio | Prompt Veo 3"""

        message = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {"type": "base64", "media_type": audio_type, "data": audio_data}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        )

        st.success("✅ Tabela Gerada com Sucesso!")
        st.markdown(message.content[0].text)

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
