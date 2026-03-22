export type Article = {
  id?: number;
  title: string;
  summary: string;
  source: string;
  link: string;
  published?: string;
  category?: string;
  region?: string;
  image_url?: string;
  cluster_id?: number;
  sources?: string[];
  related_links?: string[];
};
