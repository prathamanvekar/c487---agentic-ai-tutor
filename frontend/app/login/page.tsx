"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import axios from "axios";
import { api } from "../lib/api";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setLoading(true);
      setError("");

      const res = await api.post("/auth/login", {
        username,
        password,
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
        setError(detail || err.message || "Login failed");
        return;
      }

      setError("Network error. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen flex items-center justify-center bg-gray-900 text-white">
      <form
        onSubmit={handleLogin}
        className="bg-gray-800 p-8 rounded-xl border border-gray-700 w-96"
      >
        <h1 className="text-2xl font-bold mb-6">Login</h1>

        {error && (
          <div className="bg-red-500/20 border border-red-500 text-red-200 text-sm p-3 rounded mb-4 text-center">
            {error}
          </div>
        )}

        <input
          className="w-full bg-gray-900 p-3 mb-4 rounded border border-gray-600"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          className="w-full bg-gray-900 p-3 mb-6 rounded border border-gray-600"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          disabled={loading}
          className="w-full bg-blue-600 p-3 rounded font-bold hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Signing in..." : "Sign In"}
        </button>

        <div className="mt-6 text-center text-sm text-gray-400">
          Don&apos;t have an account?{" "}
          <Link
            href="/register"
            className="text-blue-400 hover:underline hover:text-blue-300"
          >
            Sign up
          </Link>
        </div>
      </form>
    </div>
  );
}
