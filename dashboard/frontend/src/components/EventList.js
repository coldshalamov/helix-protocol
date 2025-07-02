import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";

export default function EventList() {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    axios
      .get("/api/events")
      .then(res => setEvents(res.data))
      .catch(err => console.error(err));
  }, []);

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Events</h1>
      <ul className="space-y-1">
        {events.map(evt => (
          <li key={evt.header.statement_id}>
            <Link
              to={`/statement/${evt.header.statement_id}`}
              className="text-indigo-600 hover:underline"
            >
              {evt.header.statement_id}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
