import type { Answer } from "../types";

/** One line saying a stored answer is a recording: when it was generated, by which model, and with
 *  which prompt version (the first characters of the prompt's hash). null for a fresh answer. */
export function recordedLine(answer: Answer): string | null {
  if (!answer.cached) return null;
  const d = new Date(answer.cached.created_at);
  const date = isNaN(d.getTime()) ? answer.cached.created_at.slice(0, 10) : d.toISOString().slice(0, 10);
  const model = answer.generation?.model;
  const prompt = answer.generation?.prompt_sha256?.slice(0, 8);
  let line = `Recorded answer, generated ${date}`;
  if (model) line += ` by ${model}`;
  if (prompt) line += `, prompt version ${prompt}`;
  return `${line}. Shown as it was generated.`;
}
