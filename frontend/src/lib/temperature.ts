// The UI is strictly Fahrenheit-only everywhere (Triage form, EMR,
// Patient Portal) — the backend column is `temperature_celsius`
// (backend/app/modules/vitals/schemas.py), so every read/write through
// this file's two conversions is what keeps the two in sync. Clinical
// range: 95°F-107°F (35.0°C-41.7°C), comfortably inside the backend's own
// 30.0-45.0°C validation bound — no backend schema change needed for a
// direct Fahrenheit input to be accepted.
export const FAHRENHEIT_MIN = 95
export const FAHRENHEIT_MAX = 107

export function fahrenheitToCelsius(fahrenheit: number): number {
  return Math.round((((fahrenheit - 32) * 5) / 9) * 10) / 10
}

export function celsiusToFahrenheit(celsius: number): number {
  return Math.round(((celsius * 9) / 5 + 32) * 10) / 10
}
