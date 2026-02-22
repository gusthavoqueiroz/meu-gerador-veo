import streamlit as st
import anthropic
import base64

st.set_page_config(page_title="Gerador Veo 3 - Final", layout="wide")

st.title("🎬 Gerador de Prompts para Veo 3")

with st.sidebar:
    st.header("🔑 Configuração")
    cl_key = st.text_input("Claude API Key", type="password")
    estilo = st.text_input("Estilo Visual", value="Cinematic, 8k, realistic")

audio_file = st.file_uploader("Suba seu áudio", type=['mp3', 'wav', 'm4a', 'mp4'])

if st.button("Gerar Prompts") and audio_file and cl_key:
    try:
        client = anthropic.Anthropic(api_key=cl_key)
        
        st.info("⌛ O Claude está ouvindo seu áudio... Isso pode levar um minuto.")
        
        # Lê o arquivo e converte para base64
        audio_raw = audio_file.read()
        audio_base64 = base64.b64encode(audio_raw).decode("utf-8")
        
        # Define o tipo de mídia corretamente
        mime_type = "audio/mpeg" # padrão para mp3
        if audio_file.name.endswith("wav"): mime_type = "audio/wav"
        elif audio_file.name.endswith("m4a") or audio_file.name.endswith("mp4"): mime_type = "audio/mp4"

        # Chamada com suporte a BETA de Áudio do Claude
        message = client.beta.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4000,
            betas=["audio-2024-10-01"], # Ativa o suporte a áudio
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "audio",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": audio_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": f"Analise este áudio e crie uma tabela de prompts para o gerador de vídeo VEO 3. Divida em blocos de 8 segundos. Estilo: {estilo}. Prompts em inglês. Formato: Tempo | Texto Original | Prompt Veo 3."
                        }
                    ]
                }
            ]
        )

        st.success("✅ Tabela Gerada!")
        st.markdown(message.content[0].text)

    except Exception as e:
        st.error(f"Erro detalhado: {e}")
