import os

import gradio as gr

from src.rag_pipeline import CineMidasRAG


rag = CineMidasRAG()


def chat_with_cinemidas(
    message: str,
    history: list,
) -> str:
    """Recebe uma pergunta e devolve a resposta do CineMidas."""

    if not message or not message.strip():
        return (
            "Escreva uma pergunta sobre os serviços "
            "da Rede CineViva."
        )

    try:
        result = rag.ask(message.strip())
        answer = result["answer"]

        if result["sources"]:
            sources_text = "\n".join(
                f"- {source}"
                for source in result["sources"]
            )

            answer += (
                "\n\n**Fontes utilizadas pelo RAG:**\n"
                f"{sources_text}"
            )

        return answer

    except Exception as error:
        print(
            "Erro interno:",
            type(error).__name__,
            str(error),
        )

        return (
            "Não foi possível processar a pergunta neste momento. "
            "Tente novamente em alguns instantes."
        )


chatbot_component = gr.Chatbot(
    height=500,
    placeholder=(
        "🎬 **Bem-vindo ao CineMidas**\n\n"
        "Pergunte sobre ingressos, cancelamentos, "
        "acessibilidade, pagamentos ou outros serviços "
        "da Rede CineViva."
    ),
)

textbox_component = gr.Textbox(
    placeholder="Digite sua pergunta...",
    container=False,
)

demo = gr.ChatInterface(
    fn=chat_with_cinemidas,
    chatbot=chatbot_component,
    textbox=textbox_component,
    title="🎬 CineMidas",
    description=(
        "Assistente interno da Rede CineViva. "
        "As respostas são baseadas no Manual de Atendimento."
    ),
    examples=[
        "Até quando posso cancelar um ingresso comprado pelo aplicativo?",
        "Todas as sessões possuem audiodescrição?",
        "Posso entrar com alimentos comprados fora do cinema?",
        "Como funcionam os pontos do CineViva Club?",
    ],
    flagging_mode="never",
    save_history=False,
    concurrency_limit=1,
    api_visibility="private",
)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))

    print(
        f"CineMidas inicializado com {len(rag.chunks)} trechos."
    )

    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=False,
    )
