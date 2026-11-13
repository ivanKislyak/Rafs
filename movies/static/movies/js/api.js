class APIError extends Error {
  constructor(status, data) {
    super(`HTTP ${status}`);
    this.name = "APIError";
    this.status = status;
    this.data = data;
  }
}

function getCookie(field) {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(field + "="))
    ?.split("=")[1];
}

async function apiRequest(url, { method = "GET", body = null } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase())) {
    headers["X-CSRFToken"] = getCookie("csrftoken");
  }
  const options = {
    method: method,
    credentials: "same-origin",
    headers: headers,
    body: body !== null ? JSON.stringify(body) : null,
  };
  const response = await fetch(url, options);

  if (!response.ok) {
    const data = (await response.text()).trim();
    let dataJSON = null;
    try {
      dataJSON = JSON.parse(data);
    } catch (error) {}
    throw new APIError(response.status, dataJSON);
  }

  if (response.status === 204) {
    return { status: response.status, data: null };
  }
  const results = await response.json();
  return { status: response.status, data: results };
}
