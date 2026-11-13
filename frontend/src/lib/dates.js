export function addDays(isoDate, days) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

/** Today's calendar date in Vietnam, which is what campaign dates mean. */
export function vietnamDate(now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Ho_Chi_Minh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** A campaign cannot start in the past or end before it starts. */
export function normalizeDateRange(dateFrom, dateTo, minimumDate = vietnamDate()) {
  const from = dateFrom && dateFrom >= minimumDate ? dateFrom : minimumDate;
  const to = dateTo && dateTo >= from ? dateTo : from;
  return { dateFrom: from, dateTo: to };
}
