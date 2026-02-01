"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { api } from "../lib/api";

type DashboardCourse = {
  id: number;
  title: string;
  description?: string | null;
  created_at?: string;
  has_curriculum?: boolean;
  has_vectors?: boolean;
};

type DashboardResponse = {
  student_id: number;
  course_count: number;
  courses: DashboardCourse[];
  career_recommendation?: {
    week_start: string;
    recommendation: string;
  };
};

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<DashboardResponse>("/dashboard");
      setData(res.data);
    } catch (err: unknown) {
      console.error(err);
      if (axios.isAxiosError(err)) {
        const detail = (err.response?.data as { detail?: string } | undefined)
          ?.detail;
        setError(detail || err.message || "Failed to load dashboard");
      } else {
        setError("Failed to load dashboard");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      router.push("/login");
      return;
    }
    load();
  }, [router]);

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("student_id");
    router.push("/login");
  };

  return (
    <main className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Dashboard</h1>
            <p className="text-gray-400 text-sm">
              Your courses + weekly career recommendation.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/lobby")}
              className="text-sm px-3 py-2 rounded bg-gray-800 border border-gray-700 hover:bg-gray-700"
            >
              Lobby
            </button>
            <button
              onClick={load}
              disabled={loading}
              className="text-sm px-3 py-2 rounded bg-gray-800 border border-gray-700 hover:bg-gray-700 disabled:opacity-50"
            >
              Refresh
            </button>
            <button
              onClick={logout}
              className="text-sm px-3 py-2 rounded bg-gray-800 border border-gray-700 hover:bg-gray-700"
            >
              Logout
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-red-500/20 border border-red-500 text-red-200 text-sm p-3 rounded text-center">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6">
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-gray-400">Courses</div>
                <div className="text-xl font-semibold">
                  {data?.course_count ?? 0}
                </div>
              </div>
              <button
                onClick={() => router.push("/lobby")}
                className="text-sm px-3 py-2 rounded bg-blue-600 hover:bg-blue-700"
              >
                Create / Manage
              </button>
            </div>

            {loading && !data ? (
              <div className="text-gray-400 mt-4">Loading…</div>
            ) : (data?.courses?.length ?? 0) === 0 ? (
              <div className="text-gray-400 mt-4">
                No courses yet. Create one in the lobby.
              </div>
            ) : (
              <div className="space-y-3 mt-4">
                {data?.courses?.map((c) => {
                  const ready = !!c.has_curriculum && !!c.has_vectors;
                  return (
                    <div
                      key={c.id}
                      className="p-4 rounded-lg bg-gray-900 border border-gray-700 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="font-semibold truncate">{c.title}</div>
                        <div className="text-xs text-gray-400 mt-1">
                          Curriculum: {c.has_curriculum ? "Yes" : "No"} ·
                          Vectors: {c.has_vectors ? "Yes" : "No"}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => router.push(`/course/${c.id}/setup`)}
                          className="text-sm px-3 py-2 rounded bg-gray-800 border border-gray-700 hover:bg-gray-700"
                        >
                          Setup
                        </button>
                        <button
                          onClick={() => router.push(`/course/${c.id}`)}
                          disabled={!ready}
                          className="text-sm px-3 py-2 rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Learn
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-gray-400">
                  Career recommendation
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Cached weekly ({data?.career_recommendation?.week_start ?? ""}
                  )
                </div>
              </div>
            </div>
            <div className="mt-4 whitespace-pre-wrap text-sm text-gray-200">
              {data?.career_recommendation?.recommendation ??
                (loading ? "Loading…" : "No recommendation yet.")}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
