export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-16 text-slate-900">
      <section className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-12">
        <div className="mb-8 inline-flex rounded-full bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700">
          ASTU CampusGuide AI
        </div>

        <h1 className="text-3xl font-bold tracking-tight sm:text-5xl">
          University information, made easier to find.
        </h1>

        <p className="mt-5 text-base leading-7 text-slate-600">
          Your student-focused assistant for discovering university
          services, academic information, and learning resources.
        </p>

        <div className="mt-8 rounded-xl border border-slate-200 bg-slate-50 p-5">
          <p className="font-semibold">Project status</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Phase 1: project foundation. The frontend and backend
            are being prepared before the student assistant is built.
          </p>
        </div>

        <p className="mt-8 text-xs text-slate-500">
          Independent student project. Not an official ASTU service.
        </p>
      </section>
    </main>
  );
}
