"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { api } from "../lib/api";

type Course = {
  id: number;
  title: string;
  description?: string | null;
  owner_student_id?: number | null;
  created_at?: string;
};

export default function LobbyPage() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  const canCreate = useMemo(() => title.trim().length > 0, [title]);

  const loadCourses = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<{ courses: Course[] }>("/courses");
      setCourses(res.data?.courses ?? []);
    } catch (err: unknown) {
      console.error(err);
      if (axios.isAxiosError(err)) {
        const detail = (err.response?.data as { detail?: string } | undefined)
          ?.detail;
        setError(detail || err.message || "Failed to load courses");
      } else {
        setError("Failed to load courses");
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

    loadCourses();
  }, [router]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canCreate) return;

    setLoading(true);
    setError(null);
    try {
      const res = await api.post<{ course: Course }>("/courses", {
        title: title.trim(),
        description: description.trim(),
      });

      const created = res.data?.course;
      if (created?.id) {
        router.push(`/course/${created.id}/setup`);
        return;
      }

      await loadCourses();
      setTitle("");
      setDescription("");
    } catch (err: unknown) {
      console.error(err);
      if (axios.isAxiosError(err)) {
        const detail = (err.response?.data as { detail?: string } | undefined)
          ?.detail;
        setError(detail || err.message || "Failed to create course");
      } else {
        setError("Failed to create course");
      }
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("student_id");
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Course Lobby</h1>
            <p className="text-gray-400 text-sm">
              Create a class or pick one to continue.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm px-3 py-2 rounded bg-gray-800 border border-gray-700 hover:bg-gray-700"
            >
              Dashboard
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

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 bg-gray-800 border border-gray-700 rounded-xl p-5">
            <h2 className="font-semibold mb-4">Create a course</h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-sm text-gray-300 mb-1">
                  Title
                </label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white"
                  placeholder="e.g. Kech 101"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-300 mb-1">
                  Description (optional)
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white min-h-24"
                  placeholder="What is this course about?"
                />
              </div>
              <button
                disabled={loading || !canCreate}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? "Working..." : "Create course"}
              </button>
            </form>
          </div>

          <div className="lg:col-span-7 bg-gray-800 border border-gray-700 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold">Your courses</h2>
              <button
                onClick={loadCourses}
                disabled={loading}
                className="text-sm px-3 py-2 rounded bg-gray-900 border border-gray-700 hover:bg-gray-700 disabled:opacity-50"
              >
                Refresh
              </button>
            </div>

            {loading && courses.length === 0 ? (
              <div className="text-gray-400">Loading...</div>
            ) : courses.length === 0 ? (
              <div className="text-gray-400">
                No courses yet. Create one to get started.
              </div>
            ) : (
              <div className="space-y-3">
                {courses.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => router.push(`/course/${c.id}`)}
                    className="w-full text-left p-4 rounded-lg bg-gray-900 border border-gray-700 hover:bg-gray-800"
                  >
                    <div className="font-semibold">{c.title}</div>
                    {c.description ? (
                      <div className="text-sm text-gray-400 mt-1">
                        {c.description}
                      </div>
                    ) : null}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
