"""Interface web do CineMidas v2."""

import os
from pathlib import Path
from uuid import uuid4

import gradio as gr

from src.booking.agent_orchestrator import (
    BookingConversationAgent,
    GeminiDecisionPlanner,
    safe_user_error,
)
from src.booking.agent_tools import BookingAgentTools
from src.booking.database import connect_database
from src.booking.public_catalog import list_public_catalog
from src.booking.runtime import prepare_booking_runtime
from src.booking.web_presenter import render_catalog_cards


DATABASE_PATH = Path(os.getenv("CINEMIDAS_DB_PATH", "data/cinemidas.db"))
TMDB_API_TOKEN = os.getenv("TMDB_API_TOKEN")

runtime_status = prepare_booking_runtime(
    DATABASE_PATH,
    tmdb_token=TMDB_API_TOKEN,
)

_planner = None
_rag = None


def get_planner():
    global _planner
    if _planner is None:
        _planner = GeminiDecisionPlanner(
            os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        )
    return _planner


def current_catalog_html(limit: int = 12) -> str:
    connection = connect_database(DATABASE_PATH)
    try:
        return render_catalog_cards(
            list_public_catalog(connection, limit=limit)
        )
    finally:
        connection.close()


def chat_with_booking_agent(
    message: str,
    history: list,
    user_id: str,
    conversation_id: str,
):
    history = history or []
    user_id = user_id or f"WEB-USER-{uuid4().hex}"
    conversation_id = conversation_id or f"WEB-CONV-{uuid4().hex}"

    if not isinstance(message, str) or not message.strip():
        return "", history, current_catalog_html(), user_id, conversation_id

    connection = connect_database(DATABASE_PATH)
    try:
        tools = BookingAgentTools(
            connection,
            user_id=user_id,
            conversation_id=conversation_id,
            channel="WEB",
        )
        agent = BookingConversationAgent(tools, get_planner())
        turn = agent.handle(message.strip())

        cards = (
            render_catalog_cards(turn.payload)
            if turn.view == "catalog" and isinstance(turn.payload, list)
            else current_catalog_html()
        )
        history = history + [
            {"role": "user", "content": message.strip()},
            {"role": "assistant", "content": turn.text},
        ]
        return "", history, cards, user_id, conversation_id
    except Exception as error:
        print("Erro no agente de reservas:", type(error).__name__)
        history = history + [
            {"role": "user", "content": message.strip()},
            {
                "role": "assistant",
                "content": safe_user_error(error),
            },
        ]
        return "", history, current_catalog_html(), user_id, conversation_id
    finally:
        connection.close()


def quick_booking_action(message: str):
    def submit(history: list, user_id: str, conversation_id: str):
        return chat_with_booking_agent(
            message,
            history,
            user_id,
            conversation_id,
        )

    return submit


def chat_with_faq(message: str, history: list) -> str:
    global _rag
    if not message or not message.strip():
        return "Escreva uma pergunta sobre os serviços da Rede CineViva."

    try:
        if _rag is None:
            from src.rag_pipeline import CineMidasRAG

            _rag = CineMidasRAG()
        result = _rag.ask(message.strip())
        answer = result["answer"]
        if result["sources"]:
            answer += "\n\n**Fontes do manual:**\n" + "\n".join(
                f"- {source}" for source in result["sources"]
            )
        return answer
    except Exception as error:
        print("Erro no FAQ:", type(error).__name__)
        return "Não foi possível consultar o manual neste momento."


CSS = """
.hero {text-align:center; padding:18px 0 8px;}
.hero h1 {font-size:2.25rem; margin-bottom:4px;}
.movie-grid {display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:18px;}
.movie-card {background:#17171c; border:1px solid #34343d; border-radius:14px; overflow:hidden;}
.movie-card img,.poster-fallback {width:100%; aspect-ratio:2/3; object-fit:cover; background:#272730;}
.poster-fallback {display:flex; align-items:center; justify-content:center; font-size:56px;}
.movie-info {padding:12px;}
.movie-info h3 {font-size:1rem; margin:0 0 8px;}
.movie-info p {font-size:.83rem; color:#b9b9c4; margin:5px 0;}
.available {color:#71e1a1; font-size:.8rem; font-weight:700;}
.unavailable {color:#f5c56b; font-size:.8rem; font-weight:700;}
.notice {padding:10px 14px; border:1px solid #514926; border-radius:10px; background:#262313;}
"""


with gr.Blocks(title="CineMidas v2") as demo:
    gr.HTML(
        '<div class="hero"><h1>🎬 CineMidas</h1>'
        '<p>Filmes em cartaz e reservas conversacionais na rede fictícia CineViva.</p></div>'
    )
    gr.HTML(
        '<p class="notice"><strong>Protótipo educacional:</strong> cinemas, sessões, '
        'reservas e pagamentos são simulados. Catálogo e imagens vêm do TMDB.</p>'
    )

    user_state = gr.State("")
    conversation_state = gr.State("")

    with gr.Tabs():
        with gr.Tab("Em cartaz"):
            gr.Markdown(
                "## Catálogo atual no Brasil\n"
                "A disponibilidade nas unidades CineViva é simulada."
            )
            catalog_gallery = gr.HTML(current_catalog_html())

        with gr.Tab("Comprar com IA"):
            gr.Markdown(
                "## Reserve conversando\n"
                "Exemplo: *Quero assistir a um filme de ação.*"
            )
            booking_chat = gr.Chatbot(
                height=500,
                placeholder=(
                    "Diga o gênero ou filme que procura. Eu mostrarei "
                    "pôsteres, sessões e assentos disponíveis."
                ),
            )
            booking_input = gr.Textbox(
                placeholder="O que você quer assistir?",
                container=False,
            )
            with gr.Row():
                movies_button = gr.Button("🎬 Filmes em cartaz")
                action_button = gr.Button("🔥 Quero ação")
                orders_button = gr.Button("🎟️ Meus ingressos")
            recommendations = gr.HTML(current_catalog_html())

            booking_input.submit(
                chat_with_booking_agent,
                inputs=[
                    booking_input,
                    booking_chat,
                    user_state,
                    conversation_state,
                ],
                outputs=[
                    booking_input,
                    booking_chat,
                    recommendations,
                    user_state,
                    conversation_state,
                ],
            )

            for button, message in (
                (movies_button, "Mostre os filmes em cartaz"),
                (action_button, "Quero assistir a um filme de ação"),
                (orders_button, "Mostre meus ingressos recentes"),
            ):
                button.click(
                    quick_booking_action(message),
                    inputs=[
                        booking_chat,
                        user_state,
                        conversation_state,
                    ],
                    outputs=[
                        booking_input,
                        booking_chat,
                        recommendations,
                        user_state,
                        conversation_state,
                    ],
                )

        with gr.Tab("Dúvidas frequentes"):
            gr.ChatInterface(
                fn=chat_with_faq,
                examples=[
                    "Até quando posso cancelar um ingresso?",
                    "Todas as sessões possuem audiodescrição?",
                    "Posso entrar com alimentos comprados fora?",
                ],
                flagging_mode="never",
                save_history=False,
                api_visibility="private",
            )

    gr.Markdown(
        "Dados e imagens: TMDB. This product uses the TMDB API but is not "
        "endorsed or certified by TMDB."
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    print(
        "CineMidas v2 inicializado: "
        f"{runtime_status.catalog_movies} filmes publicáveis."
    )
    demo.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=False,
        css=CSS,
    )
