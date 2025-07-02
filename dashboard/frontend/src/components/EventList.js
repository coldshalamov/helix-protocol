import React, { useEffect, useState } from 'react';

export default function EventList() {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    fetch('/api/events')
      .then(res => res.json())
      .then(setEvents)
      .catch(err => console.error("Failed to load events", err));
  }, []);

  return (
    <div className="p-4">
      <h2 className="text-2xl font-bold mb-4">Finalized Events</h2>
      <ul className="space-y-2">
        {events.map(ev => (
          <li key={ev.id} className="p-4 bg-gray-100 rounded shadow">
            <p><strong>ID:</strong> {ev.id}</p>
            <p><strong>Statement:</strong> {ev.statement}</p>
            <p><strong>Compression:</strong> {ev.compression * 100}%</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
