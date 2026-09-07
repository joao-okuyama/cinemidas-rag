export const money = (cents) => new Intl.NumberFormat("pt-BR",
  { style: "currency", currency: "BRL" }).format(cents / 100);
export const audioLabel = (audio) => ({
  DUBBED: "Dublado", SUBTITLED: "Legendado", ORIGINAL: "Original",
}[audio] || audio);
export function sessionDate(value, timeZone = "America/Sao_Paulo") {
  return new Intl.DateTimeFormat("pt-BR", { timeZone, dateStyle: "short", timeStyle: "short" })
    .format(new Date(typeof value === "number" ? value * 1000 : value));
}
export const ratingLabel = (rating) => rating === "L" || rating === "Livre"
  ? "Livre" : rating ? `${rating} anos` : "Classificação não informada";
