import { useEffect, useId, useRef, useState } from "react";
import MovieCard from "./MovieCard";

export default function MovieCarousel({ movies, onSelect, disabled }) {
  const track = useRef(null);
  const id = useId();
  const [edges, setEdges] = useState({ start: true, end: true });
  useEffect(() => {
    const node = track.current;
    if (!node) return;
    const update = () => setEdges({
      start: node.scrollLeft <= 2,
      end: node.scrollLeft + node.clientWidth >= node.scrollWidth - 2,
    });
    update();
    node.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => { node.removeEventListener("scroll", update); observer.disconnect(); };
  }, [movies.length]);

  function move(direction) {
    const node = track.current;
    if (!node) return;
    node.scrollBy({
      left: direction * node.clientWidth * 0.8,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }

  if (!movies.length) return <p>Nenhum filme encontrado.</p>;
  return <section className="chat-carousel" aria-label="Filmes sugeridos" aria-roledescription="carrossel">
    <div className="chat-carousel__controls">
      <span>{movies.length} filme(s) · Deslize para explorar</span>
      <div>
        <button type="button" aria-label="Filmes anteriores" aria-controls={id}
          disabled={edges.start} onClick={() => move(-1)}>←</button>
        <button type="button" aria-label="Próximos filmes" aria-controls={id}
          disabled={edges.end} onClick={() => move(1)}>→</button>
      </div>
    </div>
    <ul ref={track} id={id} className="chat-carousel__track" tabIndex={0}
      aria-label="Lista de filmes, navegue com as setas"
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault(); move(event.key === "ArrowLeft" ? -1 : 1);
        }
      }}>
      {movies.map((movie) => <li className="chat-carousel__slide" key={movie.movie_id}>
        <MovieCard movie={movie} onSelect={onSelect} disabled={disabled} />
      </li>)}
    </ul>
  </section>;
}
