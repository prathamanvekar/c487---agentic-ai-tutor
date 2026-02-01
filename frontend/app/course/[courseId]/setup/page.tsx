"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import UploadCourseFile from "../../../components/UploadCourseFile";
import CurriculumView from "../../../components/CurriculumView";
import { api } from "../../../lib/api";

type CourseStatus = {
  course_id: number;
  has_curriculum: boolean;
  has_content_files: boolean;
  content_file_count: number;
  has_vectors: boolean;
};

export default function CourseSetupPage() {
  const router = useRouter();
  const params = useParams<{ courseId: string }>();

  const [curriculumRefreshNonce, setCurriculumRefreshNonce] = useState(0);
  const [status, setStatus] = useState<CourseStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const parsedCourseId = useMemo(() => {
    const raw = params?.courseId;
    const n = Number.parseInt(String(raw ?? ""), 10);
    return Number.isFinite(n) ? n : NaN;
  }, [params]);

  const loadStatus = async (courseId: number) => {
    setStatusLoading(true);
    try {
      const res = await api.get<CourseStatus>(`/course/${courseId}/status`);
      setStatus(res.data);
    } catch {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      router.push("/login");
      return;
    }

    if (!Number.isFinite(parsedCourseId)) {
      router.push("/lobby");
      return;
    }

    loadStatus(parsedCourseId);
  }, [parsedCourseId, router, curriculumRefreshNonce]);

  const readyToLearn = !!status?.has_curriculum && !!status?.has_vectors;

  if (!Number.isFinite(parsedCourseId)) return null;

  return (
    <main className="flex min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto w-full space-y-6">
        <div className="flex items-center justify-between bg-gray-800 border border-gray-700 rounded-xl px-4 py-3">
          <div>
            <div className="text-sm text-gray-400">Course setup</div>
            <div className="font-semibold">Course #{parsedCourseId}</div>
            <div className="text-xs text-gray-400 mt-1">
              Upload curriculum + content, then parse + ingest.
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm px-3 py-2 rounded bg-gray-900 border border-gray-700 hover:bg-gray-700"
            >
              Dashboard
            </button>
            <button
              onClick={() => router.push("/lobby")}
              className="text-sm px-3 py-2 rounded bg-gray-900 border border-gray-700 hover:bg-gray-700"
            >
              Lobby
            </button>
            <button
              onClick={() => router.push(`/course/${parsedCourseId}`)}
              disabled={!readyToLearn}
              className="text-sm px-3 py-2 rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              title={
                readyToLearn
                  ? "Go to learning"
                  : "Parse curriculum and ingest content first"
              }
            >
              Start learning
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 space-y-6">
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
              <div className="font-semibold mb-2">Setup status</div>
              {statusLoading ? (
                <div className="text-gray-400 text-sm">Checking…</div>
              ) : status ? (
                <div className="text-sm text-gray-300 space-y-1">
                  <div>
                    Curriculum parsed: {status.has_curriculum ? "Yes" : "No"}
                  </div>
                  <div>Content PDFs uploaded: {status.content_file_count}</div>
                  <div>
                    Vectors ingested: {status.has_vectors ? "Yes" : "No"}
                  </div>
                </div>
              ) : (
                <div className="text-gray-400 text-sm">
                  Unable to load status.
                </div>
              )}
            </div>

            <UploadCourseFile
              courseId={parsedCourseId}
              onCurriculumParsed={() => setCurriculumRefreshNonce((n) => n + 1)}
            />
          </div>

          <div className="lg:col-span-7 space-y-6">
            <CurriculumView
              courseId={parsedCourseId}
              refreshNonce={curriculumRefreshNonce}
              showStartLesson={false}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
