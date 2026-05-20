/** 推送/保存前去掉阅读态引用角标，避免进入公众号草稿摘要与正文。 */
export function pressBodyForPublish(text: string): string {
  return (text || "")
    .replace(/〔\d+〕/g, "")
    .replace(/【\d+】/g, "")
    .replace(/\[\d+\]/g, "")
    .replace(/  +/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
