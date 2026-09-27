import { useCallback, useRef, useState } from "react";
import { ask } from "./api.js";

/* =========================================================
   CONVERSATIONS
   Kept in App state so a thread (and an answer still being
   produced) survives switching pages. Nothing is persisted
   beyond the browser session.

   conversation = { id, title, turns: [turn] }
   turn = { id, question, status: "pending" | "done" | "error",
            startedAt, response, error, cancelled }
   ========================================================= */

const MAX_HISTORY_MESSAGES = 20;
const MAX_MESSAGE_CHARS = 20_000; // the backend's limit per history message

let idCounter = 0;
function newId(prefix) {
  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter}`;
}

/** Earlier answered turns as API history, oldest first, max 20 messages. */
function historyBefore(turns, turnId) {
  const messages = [];

  for (const turn of turns) {
    if (turn.id === turnId) break;
    if (turn.status !== "done" || !turn.response) continue;

    messages.push(
      { role: "user", content: turn.question.slice(0, MAX_MESSAGE_CHARS) },
      {
        role: "assistant",
        content: turn.response.answer_markdown.slice(0, MAX_MESSAGE_CHARS),
      },
    );
  }

  // Keep whole question/answer pairs.
  return messages.slice(-MAX_HISTORY_MESSAGES);
}

export function useConversations() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const controllers = useRef(new Map());

  const updateTurn = useCallback((conversationId, turnId, changes) => {
    setConversations((items) =>
      items.map((conversation) =>
        conversation.id !== conversationId
          ? conversation
          : {
              ...conversation,
              turns: conversation.turns.map((turn) =>
                turn.id === turnId ? { ...turn, ...changes } : turn,
              ),
            },
      ),
    );
  }, []);

  const run = useCallback(
    (conversationId, turn, history) => {
      const controller = new AbortController();
      controllers.current.set(turn.id, controller);

      ask(turn.question, history, controller.signal)
        .then((response) => {
          updateTurn(conversationId, turn.id, {
            status: "done",
            response,
            error: null,
          });
        })
        .catch((error) => {
          updateTurn(conversationId, turn.id, {
            status: "error",
            error: error?.message || "Something went wrong.",
            cancelled: Boolean(error?.cancelled),
          });
        })
        .finally(() => {
          controllers.current.delete(turn.id);
        });
    },
    [updateTurn],
  );

  /**
   * Send a question. It continues the active conversation unless
   * `fresh` is true or no conversation is open.
   */
  const send = useCallback(
    (rawQuestion, { fresh = false } = {}) => {
      const question = rawQuestion.trim();
      if (!question) return;

      const current = fresh
        ? null
        : conversations.find((conversation) => conversation.id === activeId);

      if (current?.turns.some((turn) => turn.status === "pending")) return;

      const turn = {
        id: newId("turn"),
        question,
        status: "pending",
        startedAt: Date.now(),
        response: null,
        error: null,
        cancelled: false,
      };

      if (current) {
        const history = historyBefore(current.turns, null);
        setConversations((items) =>
          items.map((conversation) =>
            conversation.id === current.id
              ? { ...conversation, turns: [...conversation.turns, turn] }
              : conversation,
          ),
        );
        run(current.id, turn, history);
      } else {
        const conversation = {
          id: newId("conversation"),
          title: question,
          turns: [turn],
        };
        setConversations((items) => [conversation, ...items]);
        setActiveId(conversation.id);
        run(conversation.id, turn, []);
      }
    },
    [activeId, conversations, run],
  );

  const retry = useCallback(
    (conversationId, turnId) => {
      const conversation = conversations.find((item) => item.id === conversationId);
      const turn = conversation?.turns.find((item) => item.id === turnId);
      if (!turn || turn.status === "pending") return;

      const restarted = {
        ...turn,
        status: "pending",
        startedAt: Date.now(),
        error: null,
        cancelled: false,
      };

      updateTurn(conversationId, turnId, restarted);
      run(conversationId, restarted, historyBefore(conversation.turns, turnId));
    },
    [conversations, run, updateTurn],
  );

  const cancel = useCallback((turnId) => {
    controllers.current.get(turnId)?.abort();
  }, []);

  const startNew = useCallback(() => setActiveId(null), []);

  const active =
    conversations.find((conversation) => conversation.id === activeId) || null;

  return {
    conversations,
    active,
    activeId,
    send,
    retry,
    cancel,
    startNew,
    open: setActiveId,
  };
}
