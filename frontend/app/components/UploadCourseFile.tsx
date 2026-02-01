/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState } from "react";
import axios from "axios";
import { api } from "../lib/api";

type UploadResponse = {
  saved_path: string;
  filename: string;
  course_id: number;
  file_kind?: "curriculum" | "content";
};

export type UploadCourseFileProps = {
  courseId: number;
  onCurriculumParsed?: () => void;
  onContentIngested?: () => void;
};

export default function UploadCourseFile({
  courseId,
  onCurriculumParsed,
  onContentIngested,
}: UploadCourseFileProps) {
  const [curriculumFile, setCurriculumFile] = useState<File | null>(null);
  const [contentFiles, setContentFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [curriculumUpload, setCurriculumUpload] =
    useState<UploadResponse | null>(null);
  const [contentUploads, setContentUploads] = useState<UploadResponse[]>([]);
  const [parsing, setParsing] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const uploadOne = async (file: File, fileKind: "curriculum" | "content") => {
    const formData = new FormData();
    formData.append("course_id", String(courseId));
    formData.append("file_kind", fileKind);
    formData.append("file", file);

    const res = await api.post<UploadResponse>("/upload_file", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress: (evt) => {
        const total = evt.total ?? 0;
        if (total > 0) {
          setProgress(Math.round((evt.loaded * 100) / total));
        }
      },
    });
    return res.data;
  };

  const handleUploadCurriculum = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setStatus(null);

    if (!curriculumFile) {
      setError("Please choose a curriculum/index PDF to upload.");
      return;
    }

    try {
      setUploading(true);
      setProgress(0);
      const uploaded = await uploadOne(curriculumFile, "curriculum");
      setCurriculumUpload(uploaded);
      setProgress(100);
      setStatus("Curriculum PDF uploaded. Next: Parse curriculum.");
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail =
          (err.response?.data as any)?.detail ??
          err.message ??
          "Upload failed.";
        setError(String(detail));
      } else {
        setError("Upload failed.");
      }
    } finally {
      setUploading(false);
    }
  };

  const handleUploadContent = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setStatus(null);

    if (!contentFiles.length) {
      setError("Please choose one or more content PDFs to upload.");
      return;
    }

    try {
      setUploading(true);
      setProgress(0);

      const uploaded: UploadResponse[] = [];
      for (const f of contentFiles) {
        setProgress(0);
        const one = await uploadOne(f, "content");
        uploaded.push(one);
      }

      setContentUploads((prev) => [...prev, ...uploaded]);
      setProgress(100);
      setStatus(
        `Uploaded ${uploaded.length} content PDF(s). Next: Ingest content.`,
      );
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail =
          (err.response?.data as any)?.detail ??
          err.message ??
          "Upload failed.";
        setError(String(detail));
      } else {
        setError("Upload failed.");
      }
    } finally {
      setUploading(false);
    }
  };

  const handleParseCurriculum = async () => {
    setError(null);
    setStatus(null);
    try {
      setParsing(true);
      await api.post("/parse_curriculum", {
        course_id: courseId,
        // If we have an explicit curriculum path, use it; backend also supports omitting it.
        saved_path: curriculumUpload?.saved_path,
      });
      setStatus("Curriculum parsed and saved. Curriculum panel should update.");
      onCurriculumParsed?.();
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail =
          (err.response?.data as any)?.detail ?? err.message ?? "Parse failed.";
        setError(String(detail));
      } else {
        setError("Parse failed.");
      }
    } finally {
      setParsing(false);
    }
  };

  const handleIngestContent = async () => {
    setError(null);
    setStatus(null);
    try {
      setIngesting(true);
      await api.post("/ingest_vectors", {
        course_id: courseId,
        // Backend defaults to ingesting all uploaded content PDFs.
      });
      setStatus(
        "Content ingested into vectors. You can start lessons and chat.",
      );
      onContentIngested?.();
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail =
          (err.response?.data as any)?.detail ??
          err.message ??
          "Ingest failed.";
        setError(String(detail));
      } else {
        setError("Ingest failed.");
      }
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className="bg-gray-800 p-6 rounded-xl border border-gray-700 shadow-xl">
      <h3 className="text-lg font-semibold text-white mb-4">
        Upload Course Materials
      </h3>

      <div className="text-sm text-gray-400 mb-4">Course #{courseId}</div>

      <div className="space-y-6">
        <form onSubmit={handleUploadCurriculum} className="space-y-3">
          <div className="text-sm text-gray-200 font-semibold">
            1) Curriculum / Index PDF
          </div>
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setCurriculumFile(e.target.files?.[0] ?? null)}
            className="w-full text-sm text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-gray-700 file:text-white hover:file:bg-gray-600"
          />
          {curriculumFile && (
            <div className="text-xs text-gray-400">
              Selected:{" "}
              <span className="text-gray-200">{curriculumFile.name}</span>
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={uploading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white p-3 rounded-lg transition-colors disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Upload curriculum"}
            </button>
            <button
              type="button"
              onClick={handleParseCurriculum}
              disabled={parsing || !curriculumUpload}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white p-3 rounded-lg transition-colors disabled:opacity-50"
            >
              {parsing ? "Parsing..." : "Parse curriculum"}
            </button>
          </div>

          {curriculumUpload && (
            <div className="text-xs text-gray-300 bg-gray-900/30 border border-gray-700 rounded-lg p-3 space-y-1">
              <div>
                Uploaded:{" "}
                <span className="text-gray-200">
                  {curriculumUpload.filename}
                </span>
              </div>
              <div>
                Saved:{" "}
                <span className="text-gray-400">
                  {curriculumUpload.saved_path}
                </span>
              </div>
            </div>
          )}
        </form>

        <form onSubmit={handleUploadContent} className="space-y-3">
          <div className="text-sm text-gray-200 font-semibold">
            2) Content PDFs (all chapters)
          </div>
          <input
            type="file"
            accept="application/pdf"
            multiple
            onChange={(e) => setContentFiles(Array.from(e.target.files ?? []))}
            className="w-full text-sm text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-gray-700 file:text-white hover:file:bg-gray-600"
          />

          {contentFiles.length > 0 && (
            <div className="text-xs text-gray-400">
              Selected {contentFiles.length} file(s)
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={uploading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white p-3 rounded-lg transition-colors disabled:opacity-50"
            >
              {uploading ? "Uploading..." : "Upload content"}
            </button>
            <button
              type="button"
              onClick={handleIngestContent}
              disabled={ingesting}
              className="flex-1 bg-amber-600 hover:bg-amber-700 text-white p-3 rounded-lg transition-colors disabled:opacity-50"
            >
              {ingesting ? "Ingesting..." : "Ingest content"}
            </button>
          </div>

          {contentUploads.length > 0 && (
            <div className="text-xs text-gray-300 bg-gray-900/30 border border-gray-700 rounded-lg p-3">
              <div className="font-semibold text-gray-200 mb-2">
                Uploaded content
              </div>
              <div className="space-y-1 max-h-28 overflow-auto">
                {contentUploads.map((u, idx) => (
                  <div key={`${u.saved_path}-${idx}`} className="text-gray-300">
                    - {u.filename}
                  </div>
                ))}
              </div>
            </div>
          )}
        </form>

        {(uploading || progress > 0) && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-gray-400">
              <span>Upload progress</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 bg-gray-700 rounded">
              <div
                className="h-2 bg-blue-500 rounded"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {status && (
          <div className="text-sm text-blue-200 bg-blue-900/20 border border-blue-500/40 rounded-lg p-3">
            {status}
          </div>
        )}

        {error && (
          <div className="text-sm text-red-300 bg-red-900/20 border border-red-500 rounded-lg p-3">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
