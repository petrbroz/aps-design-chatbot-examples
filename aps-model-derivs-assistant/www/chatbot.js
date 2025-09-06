import { DESIGN_AGENT_API } from "./config.js";

export function initChatbot(authProvider, urn) {
    const $chatbot = document.querySelector("#chatbot");
    $chatbot.innerHTML = `
        <div style="width: 100%; height: 100%;">
            <div id="chatbot-history" style="position: relative; top: 0; left: 0; right: 0; height: 80%; overflow-y: auto; display: flex; flex-flow: column nowrap;">
            </div>
            <div id="chatbot-prompt" style="position: relative; left: 0; right: 0; bottom: 0; height: 20%; overflow-y: hidden; display: flex; flex-flow: column nowrap;">
                <textarea id="chatbot-input" style="margin: 0.5em; margin-bottom: 0; height: 100%;">What are the top 5 elements with the largest area?</textarea>
                <div style="display: flex; flex-flow: row nowrap; align-items: center;">
                    <sl-button id="chatbot-send" variant="primary" style="margin: 0.5em; flex-grow: 1;">Send</sl-button>
                    <sl-icon-button id="chatbot-tips" name="question" label="Tips" style="margin: 0.5em 0.5em 0.5em 0;"></sl-icon-button>
                </div>
            </div>
            <sl-dialog id="chatbot-tips-dialog" label="Tips">
                <sl-button class="example" size="small" style="margin: 0.5em" pill>
                    What are the top 5 elements with the largest area?
                </sl-button>
                <sl-button class="example" size="small" style="margin: 0.5em" pill>
                    Give me the complete list of IDs of wall elements.
                </sl-button>
                <sl-button class="example" size="small" style="margin: 0.5em" pill>
                    What is the average height of doors?
                </sl-button>
                <sl-button class="example" size="small" style="margin: 0.5em" pill>
                    What is the sum of volumes of all floors?
                </sl-button>
                <sl-button slot="footer" variant="primary">Close</sl-button>
            </sl-dialog>
        </div>
    `;
    const $input = document.getElementById("chatbot-input");
    const $button = document.getElementById("chatbot-send");
    $button.addEventListener("click", async function () {
        const prompt = $input.value;
        addChatMessage("User", prompt);
        $input.value = "";
        $input.setAttribute("disabled", "true");
        $button.innerText = "Thinking...";
        $button.setAttribute("disabled", "true");

        // Create assistant message container for streaming
        const assistantCard = createStreamingChatMessage("Assistant");

        try {
            await submitPrompt(prompt, urn, authProvider, assistantCard);
        } catch (err) {
            console.error(err);
            alert("Unable to process the query. See console for more details.");
        } finally {
            $input.removeAttribute("disabled");
            $button.innerText = "Send";
            $button.removeAttribute("disabled");
        }
    });
    const tipsDialog = document.getElementById("chatbot-tips-dialog");
    const tipsOpenButton = document.getElementById("chatbot-tips");
    const tipsCloseButton = tipsDialog.querySelector(`sl-button[slot="footer"]`);
    tipsOpenButton.addEventListener("click", () => tipsDialog.show());
    tipsCloseButton.addEventListener("click", () => tipsDialog.hide());
    for (const example of tipsDialog.querySelectorAll("sl-button.example")) {
        example.addEventListener("click", function () {
            $input.value = example.innerText;
            tipsDialog.hide();
        });
    }
}

async function submitPrompt(prompt, urn, authProvider, messageCard) {
    const credentials = await authProvider.getCredentials();
    const resp = await fetch(DESIGN_AGENT_API, {
        method: "post",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            prompt,
            aps_design_urn: urn,
            aps_access_token: credentials.access_token,
        })
    });

    if (!resp.ok) {
        throw new Error(await resp.text());
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let accumulatedText = "";

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            let chunk = decoder.decode(value, { stream: true });
            for (const line of chunk.split("\n")) {
                if (line.startsWith("data:")) {
                    const data = JSON.parse(line.slice(5).trim());
                    if (data) {
                        accumulatedText += data;
                    }
                }
            }
            updateStreamingChatMessage(messageCard, accumulatedText);
        }
    } finally {
        reader.releaseLock();
    }
}

function addChatMessage(title, message) {
    const card = document.createElement("sl-card");
    card.classList.add("card-header");
    card.style.margin = "0.5em";
    message = DOMPurify.sanitize(marked.parse(message)); // Sanitize and render markdown
    card.innerHTML = `<div slot="header">${title}</div>${message}`;
    const _history = document.getElementById("chatbot-history");
    _history.appendChild(card);
    setTimeout(() => _history.scrollTop = _history.scrollHeight, 1);
}

function createStreamingChatMessage(title) {
    const card = document.createElement("sl-card");
    card.classList.add("card-header");
    card.style.margin = "0.5em";
    card.innerHTML = `<div slot="header">${title}</div><div class="message-content"></div>`;
    const _history = document.getElementById("chatbot-history");
    _history.appendChild(card);
    setTimeout(() => _history.scrollTop = _history.scrollHeight, 1);
    return card;
}

function updateStreamingChatMessage(card, text) {
    const messageContent = card.querySelector('.message-content');
    const sanitizedText = DOMPurify.sanitize(marked.parse(text)); // Sanitize and render markdown
    messageContent.innerHTML = sanitizedText;
    const _history = document.getElementById("chatbot-history");
    setTimeout(() => _history.scrollTop = _history.scrollHeight, 1);
}