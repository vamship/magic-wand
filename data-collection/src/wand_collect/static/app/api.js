// Requests to the server. A successful request resolves with the JSON body
// (or null). A failed one rejects with an ApiError that carries the `code`
// and `message` of the server's error response. A command's response only
// says whether it was accepted; its effect arrives in the next snapshot.

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export async function request(method, path, body, fetchFunction = fetch) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetchFunction(path, options);
  } catch (error) {
    throw new ApiError("network_error", "Cannot reach the application.", 0);
  }
  if (response.ok) {
    if (response.status === 204) return null;
    return response.json().catch(() => null);
  }
  let code = "error";
  let message = response.statusText || "The request failed.";
  try {
    const data = await response.json();
    if (data.error) {
      code = data.error.code;
      message = data.error.message;
    }
  } catch (error) {
    // The body was not JSON; keep the status text.
  }
  throw new ApiError(code, message, response.status);
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body ?? {}),
  put: (path, body) => request("PUT", path, body ?? {}),
  patch: (path, body) => request("PATCH", path, body ?? {}),
  delete: (path) => request("DELETE", path),
};
