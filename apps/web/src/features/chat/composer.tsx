"use client";

import { useId, type FormEvent, type KeyboardEvent } from "react";

import { Button, inputClass } from "@/components/ui";

import { MAX_QUESTION_CHARS } from "./stream";

export function Composer({
  value,
  onChange,
  onSubmit,
  busy,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (question: string) => void;
  busy: boolean;
}) {
  const fieldId = useId();
  const question = value.trim();
  const canSend = question.length > 0 && !busy;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (canSend) {
      onSubmit(question);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter adds a line. Never send while an IME is composing text.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="space-y-1.5">
      <label htmlFor={fieldId} className="sr-only">
        Your question
      </label>
      <div className="flex items-end gap-2">
        <textarea
          id={fieldId}
          rows={2}
          className={`${inputClass} resize-none`}
          placeholder="Ask about your documents, in Indonesian or English…"
          value={value}
          maxLength={MAX_QUESTION_CHARS}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <Button type="submit" disabled={!canSend}>
          {busy ? "Answering…" : "Ask"}
        </Button>
      </div>
      <p className="flex justify-between text-xs text-slate-500">
        <span>Enter to send · Shift+Enter for a new line</span>
        {value.length > MAX_QUESTION_CHARS * 0.8 ? (
          <span>
            {value.length} / {MAX_QUESTION_CHARS}
          </span>
        ) : null}
      </p>
    </form>
  );
}
