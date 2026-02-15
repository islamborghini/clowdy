import { BrowserRouter, Routes, Route } from "react-router"
import { Layout } from "@/components/layout/Layout"
import { Dashboard } from "@/pages/Dashboard"
import { Functions } from "@/pages/Functions"
import { CreateFunction } from "@/pages/CreateFunction"
import { FunctionDetail } from "@/pages/FunctionDetail"

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/functions" element={<Functions />} />
          <Route path="/functions/new" element={<CreateFunction />} />
          <Route path="/functions/:id" element={<FunctionDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
