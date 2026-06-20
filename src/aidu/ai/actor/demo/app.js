const initialTurns = [
  { role: "system", content: "You are a helpful assistant.", avatar: "System" },
  { role: "user", content: "What is the capital of France?", avatar: "Buddy" },
  { role: "assistant", content: "The capital of France is Paris.", avatar: "Robo" },
];

const actorNames = {
  system: "System",
  user: "Buddy",
  assistant: "Robo",
};

let turns = [...initialTurns];

function render() {
  document.getElementById("root").innerHTML = `
    <main class="app-shell">
      <section class="frame">
        <header class="hero">
          <p class="eyebrow">AIDU Director</p>
          <h1>Dialog Dev Sandbox</h1>
          <p class="subtitle">Monitoring live dialog turns from SSE.</p>
        </header>
        <section class="card">
          <div class="dialog-head">
            <h2>Dialog</h2>
            <div class="meta">
              <span id="status" class="badge connecting">Connecting</span>
              <span class="count">${turns.length} turns</span>
            </div>
          </div>
          <div class="turn-list">
            ${turns.map(renderTurn).join("")}
          </div>
          <div class="mt-4 flex gap-2 p-4">
            <input
              data-testid="dialog-input"
              class="flex-1 border rounded p-2"
              placeholder="Type a message..."
            />
            <button
              data-testid="send-button"
              class="px-4 py-2 bg-blue-600 text-white rounded"
            >
              Send
            </button>
          </div>
        </section>
      </section>
    </main>
  `;

  const input = document.querySelector('[data-testid="dialog-input"]');
  document.querySelector('[data-testid="send-button"]').addEventListener("click", send);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      send();
    }
  });
}

function renderTurn(turn) {
  const role = escapeHtml(turn.role ?? "message");
  const actor = escapeHtml(turn.avatar ?? actorNames[turn.role] ?? turn.role ?? "Message");
  const content = escapeHtml(turn.content ?? "");

  return `
    <article class="turn turn-${role}">
      <div class="turn-top">
        <span class="role">${role}</span>
        <span class="actor">${actor}</span>
      </div>
      <p>${content}</p>
    </article>
  `;
}

async function send() {
  const input = document.querySelector('[data-testid="dialog-input"]');
  const content = input.value.trim();
  if (!content) return;

  input.value = "";
  turns.push({ role: "user", content, avatar: actorNames.user });
  render();

  try {
    const response = await fetch("/input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "user", content }),
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const errorBody = await response.json();
        detail = errorBody.detail ?? detail;
      } catch {
        detail = await response.text() || detail;
      }
      throw new Error(detail);
    }
  } catch (error) {
    console.error("Failed to send message:", error);
    turns.push({
      role: "system",
      content: error.message,
      avatar: actorNames.system,
    });
    render();
  }
}

function connectEvents() {
  const events = new EventSource("/events");

  events.onopen = () => setStatus("connected", "Connected");
  events.onerror = () => setStatus("disconnected", "Disconnected");
  events.onmessage = (event) => {
    try {
      const turn = JSON.parse(event.data);
      turns.push({
        avatar: actorNames[turn.role] ?? turn.role,
        ...turn,
      });
      render();
      setStatus("connected", "Connected");
    } catch (error) {
      console.error("Failed to parse event:", error);
    }
  };
}

function setStatus(className, text) {
  const status = document.getElementById("status");
  if (!status) return;
  status.className = `badge ${className}`;
  status.textContent = text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

render();
connectEvents();
