// Small calculations for the calibrate page, kept apart from the markup.

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

// Where a click landed in an image, as fractions of its width and height
// (0 to 1, from the top left). `rect` is the image's bounding rectangle.
export function clickFraction(rect, clientX, clientY) {
  return {
    horizontal: clamp((clientX - rect.left) / rect.width, 0, 1),
    vertical: clamp((clientY - rect.top) / rect.height, 0, 1),
  };
}

// Keeps the readings of the last `windowS` seconds.
export function trimReadings(readings, windowS) {
  if (!readings.length) return readings;
  const newest = readings[readings.length - 1].timestampS;
  const first = readings.findIndex((r) => r.timestampS >= newest - windowS);
  return first <= 0 ? readings : readings.slice(first);
}

// The top of the speed scale: at least 1, and room for the highest speed
// and the start threshold.
export function speedScale(readings, startSpeed) {
  const highest = readings.reduce((m, r) => Math.max(m, r.speed), 0);
  return Math.max(1, highest * 1.1, startSpeed * 1.5);
}

// Pixel positions for a speed history graph: the line, and the two
// threshold lines. Time runs left to right over `windowS`; speed up.
export function graphLayout(readings, windowS, width, height, scaleMax) {
  const y = (speed) => height - (clamp(speed, 0, scaleMax) / scaleMax) * height;
  if (!readings.length) return { points: [], startY: height, endY: height };
  const newest = readings[readings.length - 1];
  const points = readings.map((r) => [
    width - ((newest.timestampS - r.timestampS) / windowS) * width,
    y(r.speed),
  ]);
  return {
    points,
    startY: y(newest.startSpeed),
    endY: y(newest.endSpeed),
  };
}
