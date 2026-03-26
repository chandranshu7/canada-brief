export type Article = {
  id?: number;
  title: string;
  summary: string;
  source: string;
  link: string;
  published?: string;
  category?: string;
  /** High-level topic (rule-based); preferred over legacy `category` when present. */
  topic_category?: string;
  region?: string;
  image_url?: string;
  /** Video URL if article has embedded video (YouTube, Vimeo, etc.) */
  video_url?: string;
  cluster_id?: number;
  sources?: string[];
  related_links?: string[];
  /** Set when loaded from bookmarks (localStorage). */
  saved_at?: string;
};
