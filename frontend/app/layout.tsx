import "./globals.css";

export const metadata = {
  title: "学習ログ駆動型AIチューター",
  description: "研究実験用AIチューター"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
