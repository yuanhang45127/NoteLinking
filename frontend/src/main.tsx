import React from 'react'
import ReactDOM from 'react-dom/client'
import { createHashRouter, RouterProvider } from 'react-router-dom'
import 'katex/dist/katex.min.css'
import './styles.css'
import { AppProvider } from './store'
import App from './App'
import NotesPage from './pages/NotesPage'
import ConceptPage from './pages/ConceptPage'
import GraphPage from './pages/GraphPage'
import ExamPage from './pages/ExamPage'
import PapersPage from './pages/PapersPage'
import SettingsPage from './pages/SettingsPage'
import GuidePage from './pages/GuidePage'

const router = createHashRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <NotesPage /> },
      { path: 'notes', element: <NotesPage /> },
      { path: 'concept', element: <ConceptPage /> },
      { path: 'graph', element: <GraphPage /> },
      { path: 'exam', element: <ExamPage /> },
      { path: 'papers', element: <PapersPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'guide', element: <GuidePage /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppProvider>
      <RouterProvider router={router} />
    </AppProvider>
  </React.StrictMode>,
)
