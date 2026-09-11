import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { Story } from "../types";

export function useStories(): Story[] {
  const [stories, setStories] = useState<Story[]>([]);
  useEffect(() => {
    let alive = true;
    api
      .stories()
      .then((s) => {
        if (alive) setStories(s);
      })
      .catch(() => {
        if (alive) setStories([]);
      });
    return () => {
      alive = false;
    };
  }, []);
  return stories;
}
