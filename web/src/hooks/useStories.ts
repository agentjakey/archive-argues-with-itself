import { useEffect, useState } from "react";
import * as api from "../lib/api";
import type { Story } from "../types";

export interface StoriesState {
  stories: Story[];
  loading: boolean;   // true until the first /stories response settles, so the hero can hold a
                      // stable placeholder instead of flashing the static hook then the example
}

export function useStories(): StoriesState {
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    api
      .stories()
      .then((s) => {
        if (alive) setStories(s);
      })
      .catch(() => {
        if (alive) setStories([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);
  return { stories, loading };
}
