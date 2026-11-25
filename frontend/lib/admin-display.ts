export function displayGroupCondition(value: unknown): string {
  if (value === "proposed") return "experimental";
  return value == null ? "-" : String(value);
}

export function displayAdminData(value: any): any {
  if (Array.isArray(value)) return value.map(displayAdminData);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]): [string, any] => [
        key.replace(/proposed/g, "experimental"),
        displayAdminData(nested),
      ]),
    );
  }
  if (typeof value === "string") return value.replace(/proposed/g, "experimental");
  return value;
}
