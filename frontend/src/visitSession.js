// A visit lasts only for this document's lifetime. Nothing is persisted in
// localStorage/sessionStorage: reloads and new tabs bootstrap a new guest.
export function createVisitSession(createGuest) {
  let token = null;
  let pending = null;
  return {
    get token() { return token; },
    start() {
      // Deduplicate React StrictMode's initial effect, not separate visits.
      if (!pending) {
        pending = Promise.resolve().then(createGuest).then((data) => {
          if (!data?.token) throw new Error("Não foi possível iniciar a visita.");
          token = data.token;
          return data;
        }).catch((error) => {
          pending = null;
          token = null;
          throw error;
        });
      }
      return pending;
    },
  };
}
