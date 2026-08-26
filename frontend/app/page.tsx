import { NewsFeed } from "@/components/NewsFeed";
import { DEFAULT_PAGE_SIZE, fetchNewsPage } from "@/lib/api";

export const revalidate = 30;

export default async function Home() {
  let initialPage = null;
  try {
    initialPage = await fetchNewsPage({
      page: 1,
      pageSize: DEFAULT_PAGE_SIZE,
      mode: "general",
      signal: AbortSignal.timeout(5_000),
    });
  } catch (error) {
    // Keep the page available during API cold starts; NewsFeed retries client-side.
    console.warn("[Home] initial feed prefetch failed", error);
  }

  return <NewsFeed initialPage={initialPage} />;
}
