"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ChatInterface from "../../components/ChatInterface";
import CurriculumView from "../../components/CurriculumView";
import { api } from "../../lib/api";

type CourseStatus = {
  course_id: number;
  has_curriculum: boolean;
  has_content_files: boolean;
  content_file_count: number;
  has_vectors: boolean;
};

export default function CoursePage() {
  const router = useRouter();
  const params = useParams<{ courseId: string }>();
  const curriculumRefreshNonce = 0;
  const [status, setStatus] = useState<CourseStatus | null>(null);

  const parsedCourseId = useMemo(() => {
    const raw = params?.courseId;
    const n = Number.parseInt(String(raw ?? ""), 10);
    return Number.isFinite(n) ? n : NaN;
  }, [params]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      router.push("/login");
      return;
    }

    if (!Number.isFinite(parsedCourseId)) {
      router.push("/lobby");
    }
  }, [parsedCourseId, router]);

  useEffect(() => {
    if (!Number.isFinite(parsedCourseId)) return;

    let cancelled = false;
    async function run() {
      try {
        const res = await api.get<CourseStatus>(
          `/course/${parsedCourseId}/status`,
        );
        if (cancelled) return;
        setStatus(res.data);

        const ready = !!res.data?.has_curriculum && !!res.data?.has_vectors;
        if (!ready) {
          router.push(`/course/${parsedCourseId}/setup`);
        }
      } catch {
        // If status fails, keep page accessible but prompt user to setup.
        setStatus(null);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [parsedCourseId, router]);

  if (!Number.isFinite(parsedCourseId)) return null;

  return (
    <main className="flex min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-4 space-y-6">
          <div className="flex items-center justify-between bg-gray-800 border border-gray-700 rounded-xl px-4 py-3">
            <div>
              <div className="text-sm text-gray-400">Selected course</div>
              <div className="font-semibold">Course #{parsedCourseId}</div>
              {status ? (
                <div className="text-xs text-gray-400 mt-1">
                  Curriculum: {status.has_curriculum ? "Yes" : "No"} · Vectors:{" "}
                  {status.has_vectors ? "Yes" : "No"}
                </div>
              ) : null}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => router.push("/dashboard")}
                className="text-sm px-3 py-2 rounded bg-gray-900 border border-gray-700 hover:bg-gray-700"
              >
                Dashboard
              </button>
              <button
                onClick={() => router.push(`/course/${parsedCourseId}/setup`)}
                className="text-sm px-3 py-2 rounded bg-gray-900 border border-gray-700 hover:bg-gray-700"
              >
                Setup
              </button>
            </div>
          </div>

          <CurriculumView
            courseId={parsedCourseId}
            refreshNonce={curriculumRefreshNonce}
            onLessonAnswer={(answer) => {
              window.dispatchEvent(
                new CustomEvent("tutor:appendMessage", {
                  detail: { role: "ai", content: answer },
                }),
              );
            }}
          />
        </div>

        <div className="lg:col-span-8">
          <ChatInterface courseId={parsedCourseId} />
        </div>
      </div>
    </main>
  );
}
