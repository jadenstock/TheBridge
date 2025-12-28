# Hevy API Read Reference (Observed)

Live responses captured with the current account and API key to clarify what we can pull. Focused on read-only endpoints.

## Auth & Conventions
- Base URL: `https://api.hevyapp.com/v1`
- Header: `api-key: <your key>` plus `accept: application/json`
- Timestamps: ISO strings (some endpoints return `Z`, others `+00:00`)
- Units: weights in kg, distances in meters, durations in seconds

## Endpoints
- `GET /workouts?start_date&end_date&page_size` — paginated workouts within range
- `GET /workouts/{workout_id}` — full detail for one workout
- `GET /exercise_history/{exercise_id}?start_date&end_date` — set-level history for one exercise template
- `GET /exercise_templates?page&pageSize` — catalog of built-in + custom templates

### Workouts list — `/workouts`
**Params:** `start_date`, `end_date` (ISO), `page_size` (int), optional `page` (1-based)  
**Response envelope:** `page`, `page_count`, `workouts: []`

Each workout:
- `id`, `title`, `routine_id` (often `null`), `description`
- `start_time`, `end_time`, `updated_at`, `created_at`
- `exercises: []`
  - `index`, `title`, `notes` (exercise-level notes from the workout log), `exercise_template_id`, `superset_id`
  - `sets: []`
    - `index`, `type` (`warmup|normal` observed), `weight_kg`, `reps`, `distance_meters`, `duration_seconds`, `rpe`, `custom_metric`

Example (trimmed):
```json
{
  "page": 1,
  "page_count": 15,
  "workouts": [
    {
      "id": "7fa3e4c4-3d8f-41fc-be5e-920ef05c38d7",
      "title": "Upper body pull and supplemental",
      "start_time": "2025-12-23T00:08:43+00:00",
      "end_time": "2025-12-23T01:10:04+00:00",
      "description": "Great workout today! Did a lot of pull based workouts...",
      "exercises": [
        {
          "title": "Face Pull",
          "notes": "",
          "exercise_template_id": "BE640BA0",
          "sets": [
            {"type": "normal", "weight_kg": 11.34, "reps": 20, "rpe": 7.5},
            {"type": "normal", "weight_kg": 13.61, "reps": 12, "rpe": 8}
          ]
        }
      ]
    }
  ]
}
```

### Workout detail — `/workouts/{id}`
Same fields as a workout in the list response, but without the pagination envelope. Exercise-level `notes` live here (and also in the list response); for example exercise `3aee1bfe-9280-4aec-ba4e-f72c2f589f45` in workout `7fa3e4c4-3d8f-41fc-be5e-920ef05c38d7` has `notes: "First time, a little odd but fun..."`. The history endpoint does **not** include notes.

### Exercise history — `/exercise_history/{exercise_id}`
**Params:** `start_date`, `end_date` (ISO)  
**Response envelope:** `exercise_history: []` (set-level rows)

Row fields (observed):
- `workout_id`, `workout_title`, `workout_start_time`, `workout_end_time`
- `exercise_template_id`
- `weight_kg`, `reps`, `distance_meters`, `duration_seconds`, `rpe`, `custom_metric`
- `set_type` (`normal|warmup` observed)

Example (trimmed):
```json
{
  "exercise_history": [
    {
      "workout_id": "7fa3e4c4-3d8f-41fc-be5e-920ef05c38d7",
      "workout_title": "Upper body pull and supplemental",
      "workout_start_time": "2025-12-23T00:08:43+00:00",
      "exercise_template_id": "BE640BA0",
      "weight_kg": 13.61,
      "reps": 12,
      "rpe": 8,
      "set_type": "normal"
    }
  ]
}
```

### Exercise templates — `/exercise_templates`
**Params:** `page` (1-based), `pageSize` (note camelCase)  
**Response envelope:** `page`, `page_count`, `exercise_templates: []`

Template fields:
- `id` (built-ins are 8-char hex; custom IDs are UUID-like)
- `title`
- `type` (`weight_reps`, `reps_only`, `duration`, `distance_duration`, `short_distance_weight`, etc.)
- `primary_muscle_group`
- `secondary_muscle_groups` (array)
- `equipment`
- `is_custom` (bool)

Example (includes a custom template):
```json
{
  "page": 5,
  "exercise_templates": [
    {"id": "218DA87C", "title": "Superman", "type": "reps_only", "equipment": "none", "is_custom": false},
    {"id": "3aee1bfe-9280-4aec-ba4e-f72c2f589f45", "title": "Supine Cable Hip Flexor Curl", "type": "weight_reps", "equipment": "machine", "is_custom": true}
  ]
}
```

## Notes & Gaps
- All observed endpoints are GET-only; no write calls documented here.
- No routine usage seen (`routine_id` always null in current data).
- Pagination: `page` + `page_count` returned for list endpoints; use `page`/`page_size` or `pageSize` as noted.
- For richer history, combine `/workouts` to discover template IDs, then `/exercise_history/{id}` for set-level trends.
