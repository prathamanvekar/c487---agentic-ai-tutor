import json
import re
from typing import Any


def _extract_json_array_best_effort(raw_text: str) -> Any:
	raw_text = (raw_text or "").strip()

	# Direct parse first
	try:
		return json.loads(raw_text)
	except Exception:
		pass

	# Strip ```json fences if present
	fenced = re.search(r"```(?:json)?\s*(\[.*\])\s*```", raw_text, flags=re.DOTALL | re.IGNORECASE)
	if fenced:
		return json.loads(fenced.group(1))

	# Fallback: parse the first [...] block
	start = raw_text.find("[")
	end = raw_text.rfind("]")
	if start != -1 and end != -1 and end > start:
		return json.loads(raw_text[start : end + 1])

	raise ValueError("No JSON array found in LLM response")


def _looks_like_heading(line: str) -> bool:
	s = (line or "").strip()
	if not s:
		return False
	if len(s) < 3:
		return False

	# Common TOC patterns
	if re.search(r"\b(chapter|unit|module|lesson|section|part)\b", s, re.IGNORECASE):
		return True

	# Starts with numbering / roman numerals
	if re.match(r"^(\d+|[ivxlcdm]+)([\.)\-:]\s+)", s, flags=re.IGNORECASE):
		return True

	# Dotted leaders or trailing page number
	if re.search(r"\.{2,}\s*\d+\s*$", s):
		return True
	if re.search(r"\s+\d+\s*$", s) and len(s.split()) >= 2:
		return True

	# Title-ish line (few words, mostly letters)
	words = s.split()
	if 2 <= len(words) <= 12:
		letters = sum(c.isalpha() for c in s)
		if letters / max(1, len(s)) > 0.5:
			return True

	return False


def parse_toc_from_pdf(pdf_path: str, max_pages: int = 8) -> list[dict[str, Any]]:
	"""Purely heuristic TOC parsing fallback.

	Returns: [{chapter_title, chapter_order, page_estimate, topics:[], learning_objectives:[]}]
	"""
	from PyPDF2 import PdfReader

	reader = PdfReader(pdf_path)
	total_pages = len(reader.pages)
	pages_to_read = min(max_pages, total_pages)

	text = "\n".join((reader.pages[i].extract_text() or "") for i in range(pages_to_read))
	lines = [ln.strip() for ln in (text or "").splitlines()]

	seen: set[str] = set()
	candidates: list[str] = []
	for ln in lines:
		if not ln:
			continue
		if len(ln) >= 200:
			continue
		if ln in seen:
			continue
		seen.add(ln)
		if _looks_like_heading(ln):
			candidates.append(ln)

	chapters: list[dict[str, Any]] = []
	order = 1
	for ln in candidates:
		# Try to pull a trailing page number
		page_estimate = None
		m = re.search(r"(\d+)\s*$", ln)
		if m:
			try:
				page_estimate = int(m.group(1))
			except Exception:
				page_estimate = None

		# Remove dotted leaders + trailing page
		title = re.sub(r"\.{2,}.*$", "", ln).strip()
		title = re.sub(r"\s+\d+\s*$", "", title).strip()
		title = re.sub(r"^(\d+|[ivxlcdm]+)([\.)\-:]\s+)", "", title, flags=re.IGNORECASE).strip()
		title = title or ln

		chapters.append(
			{
				"chapter_title": title,
				"chapter_order": order,
				"page_estimate": page_estimate,
				"topics": [],
				"learning_objectives": [],
			}
		)
		order += 1

	return chapters


def parse_toc_with_llm(pdf_path: str, llm, max_pages: int = 8) -> list[dict[str, Any]]:
	"""LLM-assisted TOC parsing.

	1) Extract first max_pages pages with PyPDF2
	2) Preprocess candidate lines
	3) Ask LLM to output JSON array only:
	   [{chapter_title, chapter_order, page_estimate, topics:[], learning_objectives:[]}]
	4) If LLM fails or returns non-JSON, fallback to parse_toc_from_pdf
	"""
	try:
		from PyPDF2 import PdfReader
	except Exception:
		# If PyPDF2 isn't available, fallback
		return parse_toc_from_pdf(pdf_path, max_pages=max_pages)

	reader = PdfReader(pdf_path)
	total_pages = len(reader.pages)
	pages_to_read = min(max_pages, total_pages)

	raw_text = "\n".join((reader.pages[i].extract_text() or "") for i in range(pages_to_read))
	lines = [ln.strip() for ln in (raw_text or "").splitlines()]

	# Preprocess: keep short lines, dedupe, keep heading-ish lines
	seen: set[str] = set()
	candidates: list[str] = []
	for ln in lines:
		if not ln:
			continue
		if len(ln) >= 200:
			continue
		if ln in seen:
			continue
		seen.add(ln)
		if _looks_like_heading(ln):
			candidates.append(ln)

	# Limit to avoid overloading prompt
	candidates = candidates[:250]
	candidate_text = "\n".join(candidates)

	system_prompt = (
		"You are a strict curriculum TOC parser. "
		"Convert the provided candidate lines (from a PDF table of contents) into an ordered JSON array. "
		"Return VALID JSON ONLY (no Markdown, no commentary, no code fences).\n\n"
		"Schema (EXACT keys):\n"
		"[\n"
		"  {\n"
		"    \"chapter_title\": \"string\",\n"
		"    \"chapter_order\": 1,\n"
		"    \"page_estimate\": 12,\n"
		"    \"topics\": [],\n"
		"    \"learning_objectives\": []\n"
		"  }\n"
		"]\n\n"
		"Rules:\n"
		"- chapter_order must start at 1 and increment by 1.\n"
		"- page_estimate must be an integer if present; use null if unknown.\n"
		"- topics and learning_objectives must be arrays (can be empty).\n"
		"- Remove dot leaders (.....) and trailing page numbers from chapter_title."
	)

	user_prompt = (
		f"PDF path: {pdf_path}\n"
		f"Pages sampled: {pages_to_read}/{total_pages}\n\n"
		"Candidate TOC lines:\n"
		"---\n"
		f"{candidate_text}\n"
		"---\n\n"
		"Return the JSON array now."
	)

	try:
		# Prefer LCEL style if available (consistent with main.py)
		try:
			from langchain_core.prompts import ChatPromptTemplate
			from langchain_core.output_parsers import StrOutputParser

			prompt = ChatPromptTemplate.from_messages(
				[("system", system_prompt), ("human", user_prompt)]
			)
			chain = prompt | llm | StrOutputParser()
			raw_llm = chain.invoke({})
		except Exception:
			# Fallback to direct invoke
			raw_llm = llm.invoke(f"{system_prompt}\n\n{user_prompt}")
			raw_llm = getattr(raw_llm, "content", raw_llm)

		parsed = _extract_json_array_best_effort(str(raw_llm))
		if isinstance(parsed, list):
			return parsed
		return parse_toc_from_pdf(pdf_path, max_pages=max_pages)
	except Exception:
		return parse_toc_from_pdf(pdf_path, max_pages=max_pages)

