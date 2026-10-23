// The core is loaded with this file's version query so an update never pairs a
// new card with a cached old core.
const { defineTouCard } = await import(`./tou-card-core.js${new URL(import.meta.url).search}`);

defineTouCard({
  domain: "deye_local",
  type: "deye-local-tou-card",
  name: "Deye Local Time Of Use",
  description: "The inverter's Time Of Use table, edited like on its screen and saved in one write.",
  documentationURL: "https://github.com/maxbanton/hass-deye-local#time-of-use-card",
  readSchedule: (slots) => slots,
  pendingMs: 30000,
});
