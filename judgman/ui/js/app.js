import { formatTimestamp, requestJson } from "./utils.js";

const eventList = document.querySelector("#events");
const watchStatus = document.querySelector("#watch-status");
const form = document.querySelector("#analyze-form");
const codeInput = document.querySelector("#code");
const inputCount = document.querySelector("#input-count");
const analyzeButton = document.querySelector("#analyze-button");
const errorMessage = document.querySelector("#error-message");
const resultPanel = document.querySelector("#result-panel");
const analysisResult = document.querySelector("#analysis-result");
const systemForm = document.querySelector("#system-form");
const systemQuestion = document.querySelector("#system-question");
const questionCount = document.querySelector("#question-count");
const systemButton = document.querySelector("#system-button");
const systemError = document.querySelector("#system-error");
const systemResultPanel = document.querySelector("#system-result-panel");
const systemResult = document.querySelector("#system-result");
const systemSnapshot = document.querySelector("#system-snapshot");
const systemData = document.querySelector("#system-data");
const QUESTION_LIMIT = 2000;

async function refreshEvents() {
  try {
    const events = await requestJson("/api/events");
    watchStatus.textContent = "Activo";
    if (events.length === 0) {
      eventList.replaceChildren(Object.assign(document.createElement("li"), {
        className: "muted",
        textContent: "Aun no hay cambios detectados.",
      }));
      return;
    }

    eventList.replaceChildren(...events.map((event) => {
      const item = document.createElement("li");
      const description = document.createElement("span");
      const time = document.createElement("time");
      description.textContent = `${event.event}: ${event.path}`;
      time.textContent = formatTimestamp(event.timestamp);
      const status = document.createElement("span");
      status.textContent = event.status;
      item.append(description, time, status);
      if (event.detail) {
        const detail = document.createElement("span");
        detail.textContent = event.detail;
        item.append(detail);
      }
      if (event.analysis) {
        const analysis = document.createElement("pre");
        analysis.className = "event-analysis";
        analysis.textContent = event.analysis;
        item.append(analysis);
      }
      return item;
    }));
  } catch (error) {
    watchStatus.textContent = "No disponible";
    console.error("No se pudieron consultar los cambios", error);
  }
}

codeInput.addEventListener("input", () => {
  inputCount.textContent = `${codeInput.value.length} / 40000`;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.hidden = true;
  resultPanel.hidden = true;
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analizando...";

  try {
    const result = await requestJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: codeInput.value }),
    });
    analysisResult.textContent = result.analysis;
    resultPanel.hidden = false;
  } catch (error) {
    errorMessage.textContent = error.message;
    errorMessage.hidden = false;
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.textContent = "Analizar";
  }
});

async function loadSystemSnapshot() {
  try {
    const snapshot = await requestJson("/api/system/snapshot");
    systemSnapshot.textContent = Object.entries(snapshot).map(([key, value]) => {
      const rendered = Array.isArray(value) ? value.join(", ") : value;
      return `${key}: ${rendered}`;
    }).join("\n");
  } catch (error) {
    systemData.hidden = true;
    if (systemForm) {
      systemForm.hidden = true;
    }
    console.error("No se pudo consultar el snapshot del sistema", error);
  }
}

systemQuestion.addEventListener("input", () => {
  questionCount.textContent = `${systemQuestion.value.length} / ${QUESTION_LIMIT}`;
});

systemForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  systemError.hidden = true;
  systemResultPanel.hidden = true;
  systemButton.disabled = true;
  systemButton.textContent = "Consultando...";

  try {
    const result = await requestJson("/api/system", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: systemQuestion.value }),
    });
    systemResult.textContent = result.answer;
    systemResultPanel.hidden = false;
  } catch (error) {
    systemError.textContent = error.message;
    systemError.hidden = false;
  } finally {
    systemButton.disabled = false;
    systemButton.textContent = "Preguntar";
  }
});

refreshEvents();
loadSystemSnapshot();
window.setInterval(refreshEvents, 4000);
