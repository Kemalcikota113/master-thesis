// @ts-check

/* global HTMLElement */
/* global customElements */
/* global CustomEvent */
/* global self */

/**
 * https://github.com/Weedshaker/event-driven-web-components-realworld-example-app/blob/master/FRONTEND_INSTRUCTIONS.md#article
 * As a page, this component becomes a domain dependent container and shall hold organisms, molecules and/or atoms
 *
 * @export
 * @class Article
 */
export default class Article extends HTMLElement {
  constructor () {
    super()

    /**
     * Listens to the event name/typeArg: 'article'
     *
     * @param {CustomEvent & {detail: import("../controllers/Article.js").ArticleEventDetail}} event
     */
    this.articleListener = event => this.render(event.detail.fetch)

    /**
     * Listens to the event name/typeArg: 'user'
     *
     * @param {CustomEvent & {detail: import("../controllers/User.js").UserEventDetail}} event
     */
    this.userListener = event => {
      event.detail.fetch.then(user => {
        if (this.shouldComponentRender(user)) this.render(undefined, user)
      }).catch(error => {
        if (this.shouldComponentRender(null)) this.render(undefined, null)
        console.log(`Error@UserFetch: ${error}`)
      })
    }
  }

  connectedCallback () {
    this.user = undefined
    this.fetchSingleArticle = undefined

    // listen for articles
    document.body.addEventListener('article', this.articleListener)
    // on every connect it will attempt to get newest articles
    this.dispatchEvent(new CustomEvent('requestArticle', {
      /** @type {import("../controllers/Article.js").RequestArticleEventDetail} */
      detail: {}, // slug gets decided at Article.js controller, could also be done by request event to router
      bubbles: true,
      cancelable: true,
      composed: true
    }))
    document.body.addEventListener('user', this.userListener)
    this.dispatchEvent(new CustomEvent('getUser', {
      bubbles: true,
      cancelable: true,
      composed: true
    }))
    // show initial loading because there is no connectCallback render execution
    if (!this.innerHTML) this.innerHTML = /* html */'<div class="article-page"><div class="banner"><div class="container">Loading...</div></div></div>'
  }

  disconnectedCallback () {
    document.body.removeEventListener('article', this.articleListener)
    document.body.removeEventListener('user', this.userListener)
    // looks nicer when cleared
    this.innerHTML = ''
  }

  /**
   * evaluates if a render is necessary
   *
   * @param {import("../../helpers/Interfaces.js").User} [user = this.user]
   * @return {boolean}
   */
  shouldComponentRender (user = this.user) {
    return user !== this.user
  }

  /**
   * renders the article
   *
   * @param {Promise<{article: import("../../helpers/Interfaces.js").SingleArticle}>} [fetchSingleArticle = this.fetchSingleArticle]
   * @param {import("../../helpers/Interfaces.js").User} [user = this.user]
   * @return {void}
   */
  render (fetchSingleArticle = this.fetchSingleArticle, user = this.user) {
    if (user !== undefined) this.user = user
    if (fetchSingleArticle) {
      this.fetchSingleArticle = fetchSingleArticle
      Promise.all([fetchSingleArticle, this.loadDependency(), this.loadChildComponents()]).then(result => {
        const [singleArticle, markdownit, children] = result
        const article = singleArticle.article
        if (!article || !article.author || !article.tagList) return (this.innerHTML = '<div class="article-page"><div class="banner"><div class="container">An error occurred rendering the article-page!</div></div></div>')
        article.author = Object.assign(article.author, { self: user && user.username === article.author.username })
        this.innerHTML = `
          <div class="article-page">

            <div class="banner">
              <div class="container">

                <h1>${article.title}</h1>

                <div class="article-meta"></div>

              </div>
            </div>

            <div class="container page">

              <div class="row article-content">
                <div class="col-md-12">
                  <div>${markdownit.render(article.body)}</div>
                  <ul class="tag-list">
                    ${article.tagList.reduce((tagListStr, tag) => (tagListStr += `
                      <li class="tag-default tag-pill tag-outline">${tag}</li>
                    `), '')}
                  </ul>
                </div>
              </div>

              <hr />

              <div class="article-actions">
                <div class="article-meta"></div>
              </div>

              <div class="row">

                <div class="col-xs-12 col-md-8 offset-md-2">

                ${user
                  ? `
                    <c-comments><m-comments user-image="${user && (user.image || '')}" user-name="${user && (user.username || '')}"></m-comments></c-comments>
                  `
                  : '<div class="col-xs-12 col-md-8 offset-md-2"><div><a href="#/login">Sign in</a> or <a href="#/register">sign up</a> to add comments on this article. </div></div>'}
                </div>
              </div>
            </div>
          </div>
        `
        /** @type {import("../atoms/ArticleMeta.js").default} */
        // @ts-ignore
        this.querySelectorAll('.article-meta').forEach(node => {
          const articleMeta = new children[0][1](article, true)
          node.replaceWith(articleMeta)
        })
        // @ts-ignore
      }).catch(error => (this.innerHTML = console.warn(error) || (error && typeof error.toString === 'function' && error.toString().includes('aborted') ? '<div class="article-page"><div class="banner"><div class="container">Loading...</div></div></div>' : '<div class="article-page"><div class="banner"><div class="container">An error occurred fetching the article!</div></div></div>')))
    }
  }

  /**
   * fetch children when first needed
   *
   * @returns {Promise<[string, CustomElementConstructor][]>}
   */
  loadChildComponents () {
    return this.childComponentsPromise || (this.childComponentsPromise = Promise.all([
      import('../atoms/ArticleMeta.js').then(
        /** @returns {[string, CustomElementConstructor]} */
        module => ['a-article-meta', module.default]
      ),
      import('../controllers/Comments.js').then(
        /** @returns {[string, CustomElementConstructor]} */
        module => ['c-comments', module.default]
      ),
      import('../molecules/Comments.js').then(
        /** @returns {[string, CustomElementConstructor]} */
        module => ['m-comments', module.default]
      )
    ]).then(elements => {
      elements.forEach(element => {
        // don't define already existing customElements
        // @ts-ignore
        if (!customElements.get(element[0])) customElements.define(...element)
      })
      return elements
    }))
  }

  /**
   * fetch dependency
   *
   * @returns {Promise<{render:(string)=>string}>}
   */
  loadDependency () {
    return this.dependencyPromise || (this.dependencyPromise = new Promise(resolve => {
      // needs markdown
      if ('markdownit' in self === false) {
        const script = document.createElement('script')
        // https://github.com/markdown-it/markdown-it
        script.src = 'https://cdn.jsdelivr.net/npm/markdown-it/dist/markdown-it.min.js'
        // @ts-ignore
        script.onload = () => resolve(new self.markdownit()) // eslint-disable-line
        document.head.appendChild(script)
      } else {
        // @ts-ignore
        resolve(new self.markdownit()) // eslint-disable-line
      }
    }))
  }
}
