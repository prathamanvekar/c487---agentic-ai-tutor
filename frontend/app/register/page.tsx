"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import axios from "axios";
import { api } from "../lib/api";

export default function Register() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [learningStyle, setLearningStyle] = useState("visual");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await api.post("/auth/signup", {
        username,
        password,
        learning_style: learningStyle,
      });

      const token = String(res.data?.access_token ?? "");
      const studentId = res.data?.student_id;
      if (token) localStorage.setItem("token", token);
      if (studentId != null)
        localStorage.setItem("student_id", String(studentId));

      router.push("/dashboard");
    } catch (err: unknown) {
      console.error(err);

      if (axios.isAxiosError(err)) {
        const detail = (err.response?.data as { detail?: string } | undefined)
          ?.detail;
        setError(detail || err.message || "Registration failed");
        return;
      }

      setError("Network error. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center text-white p-4">
      <div className="bg-gray-800 p-8 rounded-xl shadow-2xl w-full max-w-md border border-gray-700">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-blue-500">AI Tutor</h1>
          <p className="text-gray-400 mt-2">Create your student account</p>
        </div>

        {error && (
          <div className="bg-red-500/20 border border-red-500 text-red-200 text-sm p-3 rounded mb-4 text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleRegister} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Username
            </label>
            <input
              type="text"
              required
              className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
              placeholder="Enter a username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Password
            </label>
            <input
              type="password"
              required
              className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
              placeholder="Choose a secure password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Learning style
            </label>
            <select
              className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
              value={learningStyle}
              onChange={(e) => setLearningStyle(e.target.value)}
            >
              <option value="visual">Visual</option>
              <option value="auditory">Auditory</option>
              <option value="reading">Reading</option>
              <option value="kinesthetic">Kinesthetic</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Creating Account..." : "Sign Up"}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-gray-400">
          Already have an account?{" "}
          <Link
            href="/login"
            className="text-blue-400 hover:underline hover:text-blue-300"
          >
            Log in here
          </Link>
        </div>
      </div>
    </div>
  );
}
