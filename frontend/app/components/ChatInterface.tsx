"use client";
import { useState, useRef, useEffect } from "react";
import { Send, Bot, BookOpen } from "lucide-react";
import { api } from "../lib/api";

// 1. Define the shape of the Quiz Data
interface QuizData {
  question: string;
  options: string[];
  correct_answer: number;
  topic: string;
}

// 2. Update Message interface to use QuizData
interface Message {
  role: "user" | "ai";
  content: string;
  type?: "text" | "quiz" | "feedback";
  quizData?: QuizData;
}

export type ChatInterfaceProps = {
  courseId: number;
};

type ChatTurn = {
  role: "user" | "ai";
  content: string;
};

export default function ChatInterface({ courseId }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "ai",
      content:
        "Hello! I am your AI Tutor. Ask me about any topic to start learning.",
      type: "text",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Allow other components (e.g. CurriculumView) to append messages into the chat.
  useEffect(() => {
    const handler = (evt: Event) => {
      const ce = evt as CustomEvent<{ role?: "user" | "ai"; content?: string }>;
      const role = ce.detail?.role ?? "ai";
      const content = ce.detail?.content ?? "";
      if (!content) return;
      setMessages((prev) => [...prev, { role, content, type: "text" }]);
    };

    window.addEventListener("tutor:appendMessage", handler as EventListener);
    return () =>
      window.removeEventListener(
        "tutor:appendMessage",
        handler as EventListener,
      );
  }, []);

  // Allow other components (e.g. CurriculumView) to set the current active topic/chapter.
  useEffect(() => {
    const handler = (evt: Event) => {
      const ce = evt as CustomEvent<{ topic?: string }>;
      const topic = (ce.detail?.topic ?? "").trim();
      if (!topic) return;
      setActiveTopic(topic);
    };

    window.addEventListener("tutor:setActiveTopic", handler as EventListener);
    return () =>
      window.removeEventListener(
        "tutor:setActiveTopic",
        handler as EventListener,
      );
  }, []);

  const buildChatHistory = (msgs: Message[]): ChatTurn[] => {
    // Session-only memory: keep only the recent text turns.
    const turns = msgs
      .filter((m) => m.type === "text")
      .map((m) => ({ role: m.role, content: m.content }));
    return turns.slice(-12);
  };

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMsg = {
      role: "user" as const,
      content: input,
      type: "text" as const,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const nextMessages = [...messages, userMsg];
      const chatHistory = buildChatHistory(nextMessages);

      // Normal Teaching Request
      const response = await api.post("/teach", {
        query: input,
        course_id: courseId,
        active_topic: activeTopic,
        chat_history: chatHistory,
      });

      const aiMsg = {
        role: "ai" as const,
        content: response.data.answer,
        type: "text" as const,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: "Error connecting to tutor.", type: "text" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const startQuiz = async () => {
    // Prefer the active chapter/topic; otherwise fall back to the last user message.
    const lastUserText = messages
      .filter((m) => m.role === "user" && m.type === "text")
      .pop()?.content;
    const topic = (activeTopic ?? lastUserText ?? "").trim();

    if (!topic) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content:
            "Pick a chapter first (click 'Start lesson') or ask a specific topic, then try the quiz again.",
          type: "text",
        },
      ]);
      return;
    }

    setLoading(true);
    try {
      const chatHistory = buildChatHistory(messages);
      const response = await api.post("/quiz", {
        query: topic,
        course_id: courseId,
        active_topic: activeTopic,
        chat_history: chatHistory,
      });

      const quizMsg: Message = {
        role: "ai",
        content: "Quiz Time!",
        type: "quiz",
        quizData: {
          question: response.data.question,
          options: response.data.options,
          correct_answer: response.data.correct_answer,
          topic,
        },
      };
      setMessages((prev) => [...prev, quizMsg]);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // 3. FIXED: Explicitly typed 'quizData' to remove the "any" error
  const handleOptionClick = async (optionIndex: number, quizData: QuizData) => {
    setLoading(true);
    const selectedOptionText = quizData.options[optionIndex];
    const correctOptionText = quizData.options[quizData.correct_answer];

    try {
      const response = await api.post("/grade", {
        student_id: 1,
        course_id: courseId,
        topic: quizData.topic,
        question: quizData.question,
        student_answer: selectedOptionText,
        correct_answer: correctOptionText,
      });

      const feedbackMsg: Message = {
        role: "ai",
        content: response.data.feedback,
        type: "feedback",
      };
      setMessages((prev) => [...prev, feedbackMsg]);

      // Optional: Trigger a dashboard refresh event if you add that later
      // window.dispatchEvent(new Event("quizCompleted"));
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-150 w-full bg-gray-800 rounded-xl shadow-xl border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="bg-gray-750 p-4 border-b border-gray-600 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <Bot className="w-6 h-6 text-blue-400" />
          <h2 className="text-white font-semibold">AI Tutor Agent</h2>
        </div>
        <button
          onClick={startQuiz}
          className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1 rounded text-sm flex items-center gap-2 transition-colors"
        >
          <BookOpen className="w-4 h-4" /> Take Quiz
        </button>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-gray-600">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
          >
            {/* Message Bubble */}
            <div
              className={`max-w-[85%] p-3 rounded-lg ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 text-gray-100"
              } ${msg.type === "feedback" ? (msg.content.includes("Incorrect") ? "border border-red-500 bg-red-900/20" : "border border-green-500 bg-green-900/20") : ""}`}
            >
              {/* Text Content */}
              {msg.type !== "quiz" && (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {msg.content}
                </p>
              )}

              {/* Quiz UI */}
              {msg.type === "quiz" && msg.quizData && (
                <div className="space-y-3 w-full min-w-75">
                  <p className="font-semibold text-white">
                    {msg.quizData.question}
                  </p>
                  <div className="grid grid-cols-1 gap-2 mt-2">
                    {msg.quizData.options.map((option, optIdx) => (
                      <button
                        key={optIdx}
                        // 4. FIXED: Added '!' to assert quizData is not undefined (guaranteed by the check above)
                        onClick={() => handleOptionClick(optIdx, msg.quizData!)}
                        className="text-left p-3 rounded bg-gray-800 hover:bg-gray-600 border border-gray-600 transition-all text-sm"
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Avatar label for clarity */}
            <span className="text-xs text-gray-500 mt-1 mr-1">
              {msg.role === "user" ? "You" : "AI Tutor"}
            </span>
          </div>
        ))}
        {loading && (
          <div className="text-gray-400 text-sm animate-pulse ml-2">
            Agent is thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-gray-750 border-t border-gray-600 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder="Ask about a topic..."
          className="flex-1 bg-gray-900 text-white p-3 rounded-lg border border-gray-600 focus:outline-none focus:border-blue-500 placeholder-gray-500"
        />
        <button
          onClick={sendMessage}
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-700 text-white p-3 rounded-lg transition-colors disabled:opacity-50"
        >
          <Send className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
