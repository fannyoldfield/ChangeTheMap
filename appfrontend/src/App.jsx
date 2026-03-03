import { useState } from 'react'
import axios from 'axios'
import { MapContainer, Marker, TileLayer, useMapEvents } from 'react-leaflet'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  LineElement,
  CategoryScale,
  LinearScale,
  PointElement,
  Legend,
  Tooltip,
} from 'chart.js'

ChartJS.register(LineElement, CategoryScale, LinearScale, PointElement, Legend, Tooltip)

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function LocationPicker({ onPick }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng)
    },
  })
  return null
}

export default function App() {
  const [lat, setLat] = useState(52.52)
  const [lon, setLon] = useState(13.405)
  const [marker, setMarker] = useState([52.52, 13.405])
  const [baselineStart, setBaselineStart] = useState('2019-06-01')
  const [baselineEnd, setBaselineEnd] = useState('2019-06-30')
  const [currentStart, setCurrentStart] = useState('2024-06-01')
  const [currentEnd, setCurrentEnd] = useState('2024-06-30')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const onMapPick = ({ lat, lng }) => {
    setLat(lat)
    setLon(lng)
    setMarker([lat, lng])
  }

  const submit = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const { data } = await axios.post(`${API_URL}/analyze`, {
        latitude: Number(lat),
        longitude: Number(lon),
        baseline_start: baselineStart,
        baseline_end: baselineEnd,
        current_start: currentStart,
        current_end: currentEnd,
      })
      setResult(data)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  const chartData = result
    ? {
        labels: [...result.time_series.baseline, ...result.time_series.current].map((d) => d.date),
        datasets: [
          {
            label: 'Baseline NDVI',
            data: result.time_series.baseline.map((d) => d.ndvi),
            borderColor: 'green',
          },
          {
            label: 'Current NDVI',
            data: result.time_series.current.map((d) => d.ndvi),
            borderColor: 'orange',
          },
        ],
      }
    : null

  return (
    <div style={{ padding: '1rem', fontFamily: 'sans-serif' }}>
      <h2>Green Pixels Europe</h2>
      <p>Sentinel-2 NDVI and Sentinel-3 LST comparison prototype</p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
        <label>Latitude<input value={lat} onChange={(e) => setLat(e.target.value)} /></label>
        <label>Longitude<input value={lon} onChange={(e) => setLon(e.target.value)} /></label>
        <button onClick={submit} disabled={loading}>{loading ? 'Processing...' : 'Analyze'}</button>

        <label>Baseline Start<input type="date" value={baselineStart} onChange={(e) => setBaselineStart(e.target.value)} /></label>
        <label>Baseline End<input type="date" value={baselineEnd} onChange={(e) => setBaselineEnd(e.target.value)} /></label>
        <span />

        <label>Current Start<input type="date" value={currentStart} onChange={(e) => setCurrentStart(e.target.value)} /></label>
        <label>Current End<input type="date" value={currentEnd} onChange={(e) => setCurrentEnd(e.target.value)} /></label>
      </div>

      <div style={{ height: 360, marginTop: '1rem' }}>
        <MapContainer center={marker} zoom={11} style={{ height: '100%' }}>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <Marker position={marker} />
          <LocationPicker onPick={onMapPick} />
        </MapContainer>
      </div>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {result && (
        <div>
          <h3>Results</h3>
          <pre>{JSON.stringify({
            location: result.location,
            baseline_ndvi: result.baseline_ndvi,
            current_ndvi: result.current_ndvi,
            ndvi_change: result.ndvi_change,
            baseline_lst: result.baseline_lst,
            current_lst: result.current_lst,
            lst_anomaly: result.lst_anomaly,
          }, null, 2)}</pre>

          {chartData && <Line data={chartData} />}
        </div>
      )}
    </div>
  )
}
