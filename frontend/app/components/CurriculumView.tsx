"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

type ParsedChapter = {
  chapter_title: string;
  chapter_order: number;
  page_start: number;
  page_end: number;
  topics: string[];
  learning_objectives: string[];
};

type ParsedCurriculum = {
  course_title: string;
  source_file: string;
  chapters: ParsedChapter[];
};

type CurriculumTopicRow = {
  id: number;
  course_id: number;
  topic_order: number;
  title: string;
  subtopic: string | null;
  source_file: string | null;
  page_number: number | null;
  created_at: string;
};

export type CurriculumViewProps = {
  courseId: number;
  parsedJson?: ParsedCurriculum;
  onLessonAnswer?: (answer: string, chapterTitle: string) => void;
  refreshNonce?: number;
  showStartLesson?: boolean;
};

function normalize(s: string) {
  return (s || "").toLowerCase().trim();
}

export default function CurriculumView({
  courseId,
  parsedJson,
  onLessonAnswer,
  refreshNonce,
  showStartLesson = true,
}: CurriculumViewProps) {
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chapters, setChapters] = useState<ParsedChapter[]>(
    parsedJson?.chapters ?? [],
  );
  const [activeLesson, setActiveLesson] = useState<string | null>(null);
  const [lessonAnswer, setLessonAnswer] = useState<string | null>(null);

  // If parsedJson changes, prefer it.
  useEffect(() => {
    if (parsedJson?.chapters?.length) {
      setChapters(parsedJson.chapters);
      setError(null);
    }
  }, [parsedJson]);

  // If parsedJson not provided, fetch from GET /course/{id}/topics and map into chapters.
  useEffect(() => {
    const shouldFetch = !parsedJson;
    if (!shouldFetch) return;

    let cancelled = false;

    async function run() {
      try {
        setLoading(true);
        setError(null);

        const res = await api.get<{
          course_id: number;
          topics: CurriculumTopicRow[];
        }>(`/course/${courseId}/topics`);

        if (cancelled) return;

        const rows = (res.data.topics ?? [])
          .slice()
          .sort((a, b) => a.topic_order - b.topic_order);

        // Group rows by chapter title. Rows with subtopic != null become topics.
        const byTitle = new Map<
          string,
          { order: number; page: number; topics: string[] }
        >();
        for (const row of rows) {
          const title = (row.title || "").trim();
          if (!title) continue;

          const existing = byTitle.get(title);
          const page = row.page_number ?? 1;
          if (!existing) {
            byTitle.set(title, {
              order: row.topic_order,
              page,
              topics: row.subtopic ? [row.subtopic] : [],
            });
          } else {
            if (row.subtopic) existing.topics.push(row.subtopic);
            existing.order = Math.min(existing.order, row.topic_order);
          }
        }

        // Sort chapters by first appearance in topic_order, but display as 1..N.
        const sorted = Array.from(byTitle.entries())
          .map(([title, info]) => ({
            title,
            sortOrder: info.order,
            page: info.page,
            topics: info.topics,
          }))
          .sort((a, b) => a.sortOrder - b.sortOrder);

        const mapped: ParsedChapter[] = sorted.map((ch, idx) => ({
          chapter_title: ch.title,
          chapter_order: idx + 1,
          page_start: ch.page,
          page_end: ch.page,
          topics: ch.topics,
          learning_objectives: [],
        }));

        setChapters(mapped);
      } catch {
        setError(
          "Failed to load curriculum. Make sure the backend is running and the course has topics.",
        );
      } finally {
        setLoading(false);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [courseId, parsedJson, refreshNonce]);

  const filteredChapters = useMemo(() => {
    const q = normalize(filter);
    if (!q) return chapters;
    return chapters.filter((ch) => {
      const haystack = [
        ch.chapter_title,
        ...(ch.topics ?? []),
        ...(ch.learning_objectives ?? []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [chapters, filter]);

  const startLesson = async (chapter: ParsedChapter) => {
    try {
      setActiveLesson(chapter.chapter_title);
      setLessonAnswer(null);
      setError(null);

      window.dispatchEvent(
        new CustomEvent("tutor:setActiveTopic", {
          detail: { topic: chapter.chapter_title },
        }),
      );

      const res = await api.post("/teach", {
        student_id: 1,
        query: chapter.chapter_title,
        course_id: courseId,
        active_topic: chapter.chapter_title,
      });

      const answer = String(res.data?.answer ?? "");
      setLessonAnswer(answer);

      if (onLessonAnswer) {
        onLessonAnswer(answer, chapter.chapter_title);
      } else {
        window.dispatchEvent(
          new CustomEvent("tutor:appendMessage", {
            detail: { role: "ai", content: answer },
          }),
        );
      }
    } catch {
      setError(
        "Failed to start lesson. Is the backend running and vectors ingested for this course?",
      );
    } finally {
      setActiveLesson(null);
    }
  };

  return (
    <div className="bg-gray-800 rounded-xl shadow-xl border border-gray-700 overflow-hidden">
      <div className="bg-gray-750 p-4 border-b border-gray-600">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-white font-semibold">Curriculum</h3>
            <div className="text-xs text-gray-400">Course ID: {courseId}</div>
          </div>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search chapters..."
            className="bg-gray-900 text-white px-3 py-2 rounded-lg border border-gray-600 focus:outline-none focus:border-blue-500 placeholder-gray-500 text-sm w-56"
          />
        </div>
      </div>

      <div className="p-4 space-y-3">
        {loading && (
          <div className="text-gray-400 text-sm animate-pulse">
            Loading curriculum…
          </div>
        )}
        {error && (
          <div className="text-sm text-red-300 bg-red-900/20 border border-red-500 rounded-lg p-3">
            {error}
          </div>
        )}

        {!loading && !error && filteredChapters.length === 0 && (
          <div className="text-gray-400 text-sm">
            No chapters match your filter.
          </div>
        )}

        {!loading && !error && filteredChapters.length > 0 && (
          <div className="space-y-3">
            {filteredChapters.map((ch) => (
              <div
                key={`${ch.chapter_order}-${ch.chapter_title}`}
                className="bg-gray-700/40 border border-gray-600 rounded-lg p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm text-gray-300">
                      Chapter {ch.chapter_order}
                    </div>
                    <div className="text-white font-semibold truncate">
                      {ch.chapter_title}
                    </div>
                    <div className="text-xs text-gray-400 mt-1">
                      Pages: {ch.page_start}–{ch.page_end}
                    </div>
                  </div>

                  {showStartLesson ? (
                    <button
                      onClick={() => startLesson(ch)}
                      disabled={!!activeLesson}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg text-sm transition-colors disabled:opacity-50"
                    >
                      {activeLesson === ch.chapter_title
                        ? "Starting…"
                        : "Start lesson"}
                    </button>
                  ) : null}
                </div>

                {ch.learning_objectives?.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs text-gray-300 font-semibold mb-1">
                      Learning objectives
                    </div>
                    <ul className="text-sm text-gray-200 space-y-1">
                      {ch.learning_objectives.map((lo, idx) => (
                        <li key={idx} className="text-gray-200">
                          - {lo}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {ch.topics?.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs text-gray-300 font-semibold mb-1">
                      Topics
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {ch.topics.slice(0, 12).map((t, idx) => (
                        <span
                          key={idx}
                          className="text-xs text-gray-100 bg-gray-800 border border-gray-600 rounded px-2 py-1"
                        >
                          {t}
                        </span>
                      ))}
                      {ch.topics.length > 12 && (
                        <span className="text-xs text-gray-400">
                          +{ch.topics.length - 12} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {lessonAnswer && (
          <div className="bg-gray-700 text-gray-100 rounded-lg border border-gray-600 p-4">
            <div className="text-xs text-gray-400 mb-2">
              Lesson answer (latest)
            </div>
            <div className="whitespace-pre-wrap text-sm leading-relaxed">
              {lessonAnswer}
            </div>
          </div>
        )}
      </div>

      {/*
        Integration options:

        1) Render on the right panel in app/page.tsx:

          import CurriculumView from "./components/CurriculumView";

          <CurriculumView
            courseId={1}
            onLessonAnswer={(answer) => {
              // Option A: append into ChatInterface via parent state
              // Option B: dispatch event used by ChatInterface listener
              console.log(answer);
            }}
          />

        2) If you don’t pass onLessonAnswer, CurriculumView dispatches:
           window.dispatchEvent(new CustomEvent("tutor:appendMessage", { detail: { role: "ai", content: answer }}))

        3) If you have parsed JSON from /parse_curriculum, pass it as parsedJson.
      */}
    </div>
  );
}
