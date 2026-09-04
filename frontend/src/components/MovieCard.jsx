export default function MovieCard({ movie, selected, onSelect }) {
  const details = [
    movie.runtime_minutes ? `${movie.runtime_minutes} min` : null,
    movie.age_rating ? `${movie.age_rating} anos` : "Livre ou não informada",
  ].filter(Boolean);

  return (
    <button
      className={`movie-card ${selected ? "movie-card--selected" : ""}`}
      type="button"
      onClick={() => onSelect(movie)}
      aria-pressed={selected}
    >
      <div className="movie-card__poster">
        {movie.poster_url ? (
          <img src={movie.poster_url} alt={`Pôster de ${movie.title}`} />
        ) : (
          <span aria-hidden="true">🎬</span>
        )}
        <span className="movie-card__availability">Sessões disponíveis</span>
      </div>
      <div className="movie-card__body">
        <h3>{movie.title}</h3>
        <p>{details.join(" · ")}</p>
        <p className="movie-card__genres">
          {movie.genres?.slice(0, 3).join(" · ") || "Gênero não informado"}
        </p>
      </div>
    </button>
  );
}
