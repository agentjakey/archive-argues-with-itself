import type { Story } from "../types";

/** The story shown at the threshold: the one the author marked for the hero surface, else none. */
export function heroStory(stories: Story[]): Story | null {
  return stories.find((s) => s.surfaces?.includes("hero")) ?? null;
}

/** Gallery cards: stories marked for the gallery, without the one already shown as the hero. */
export function galleryStories(stories: Story[]): Story[] {
  const hero = heroStory(stories);
  return stories.filter((s) => s !== hero && s.surfaces?.includes("gallery"));
}

/** Stories the kiosk attract loop may cycle through. */
export function attractStories(stories: Story[]): Story[] {
  return stories.filter((s) => s.surfaces?.includes("attract"));
}

/** The question a story's answer is asked with; differs from the shown question only for a
 *  corrected story whose stored answer is kept unedited beside a dated note. */
export function askedQuestion(story: Story): string {
  return story.answer_question ?? story.question;
}
