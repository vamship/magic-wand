// The End session button. Ending is final: the session accepts no more
// samples and cannot be resumed (its samples can still be reviewed and
// edited), so the button asks for confirmation first. It ends the session
// it is given by id, whether or not that session is the loaded one.

import { api } from "./api.js";
import { html } from "./html.js";

export function endConfirmation(name) {
  return (
    `End the session "${name || "(unnamed)"}"? It cannot be resumed ` +
    "afterwards, but its samples can still be reviewed and edited."
  );
}

// `onEnded` runs after the server accepted the request.
export function EndButton({ id, name, notices, onEnded, label, title }) {
  const end = async () => {
    if (!window.confirm(endConfirmation(name))) return;
    // A successful command resolves with null; a failed one with undefined
    // (its error is already shown as a notice).
    const done = await notices.attempt(() =>
      api.post(`/api/sessions/${id}/end`),
    );
    if (done !== undefined && onEnded) onEnded();
  };
  const hint = title || "End this session for good";
  return html`<button title=${hint} onClick=${end}>
    ${label || "End session"}
  </button>`;
}
