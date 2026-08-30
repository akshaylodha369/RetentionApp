
// =========================================================
// RETENTION APP - static/app.js
// =========================================================


// =========================================================
// STATE
// =========================================================

let allBusinesses = [];

let currentTab = "nearby";
let currentCategory = "all";
let searchText = "";


// =========================================================
// ELEMENTS
// =========================================================

const searchInput =
    document.getElementById("searchInput");

const businessList =
    document.getElementById("businessList");

const sectionTitle =
    document.getElementById("sectionTitle");

const nearbyTab =
    document.getElementById("nearbyTab");

const followingTab =
    document.getElementById("followingTab");

const offersTab =
    document.getElementById("offersTab");

const filterButtons =
    document.querySelectorAll(".filter-btn");

const homeNav =
    document.getElementById("homeNav");

const profileNav =
    document.getElementById("profileNav");


// =========================================================
// LOAD SAVED BUSINESSES
// =========================================================

async function loadBusinesses() {

    sectionTitle.textContent =
        "Businesses";

    businessList.innerHTML = `
        <div class="business-card">
            <div>
                <h3>Loading businesses...</h3>
                <p>Please wait.</p>
            </div>
        </div>
    `;

    try {

        const response =
            await fetch("/api/businesses");

        if (!response.ok) {

            throw new Error(
                "Failed to load businesses"
            );
        }

        allBusinesses =
            await response.json();

        console.log(
            "Saved businesses:",
            allBusinesses
        );

        renderBusinesses();

    } catch (error) {

        console.error(
            "Business loading error:",
            error
        );

        businessList.innerHTML = `
            <div class="business-card">
                <div>
                    <h3>Unable to load businesses</h3>
                    <p>
                        Please refresh the page.
                    </p>
                </div>
            </div>
        `;
    }
}


// =========================================================
// FILTER BUSINESSES
// =========================================================

function getFilteredBusinesses() {

    let businesses =
        [...allBusinesses];


    // CATEGORY FILTER

    if (
        currentCategory !== "all"
    ) {

        businesses =
            businesses.filter(
                business =>

                    String(
                        business.category || ""
                    )
                    .toLowerCase()
                    .includes(
                        currentCategory.toLowerCase()
                    )
            );
    }


    // SEARCH FILTER

    if (
        searchText.trim()
    ) {

        const query =
            searchText
                .trim()
                .toLowerCase();

        businesses =
            businesses.filter(
                business => {

                    const name =
                        String(
                            business.name || ""
                        ).toLowerCase();

                    const category =
                        String(
                            business.category || ""
                        ).toLowerCase();

                    const address =
                        String(
                            business.address || ""
                        ).toLowerCase();

                    return (
                        name.includes(query) ||
                        category.includes(query) ||
                        address.includes(query)
                    );
                }
            );
    }


    return businesses;
}


// =========================================================
// RENDER BUSINESSES
// =========================================================

function renderBusinesses() {

    // FOLLOWING TAB

    if (
        currentTab === "following"
    ) {

        loadFollowingBusinesses();

        return;
    }


    let businesses =
        getFilteredBusinesses();


    // OFFERS TAB

    if (
        currentTab === "offers"
    ) {

        businesses =
            businesses.filter(
                business =>
                    business.offer &&
                    String(
                        business.offer
                    ).trim() !== ""
            );
    }


    // NO RESULTS

    if (
        !businesses.length
    ) {

        businessList.innerHTML = `
            <div class="business-card">
                <div>
                    <h3>No businesses found</h3>
                    <p>
                        Try another search or category.
                    </p>
                </div>
            </div>
        `;

        return;
    }


    // RENDER

    businessList.innerHTML =
        businesses
            .map(
                business =>
                    createBusinessCard(
                        business
                    )
            )
            .join("");
}


// =========================================================
// BUSINESS CARD
// =========================================================

function createBusinessCard(
    business
) {

    const icon =
        getCategoryIcon(
            business.category
        );


    const offerText =
        business.offer
            ? `🎟️ ${escapeHtml(
                business.offer
            )}`
            : "No active offer";


    return `
        <a
            href="/static/business.html?id=${business.id}"
            class="business-link"
        >

            <div class="business-card">

                <div>

                    <h3>
                        ${icon}
                        ${escapeHtml(
                            business.name
                        )}
                    </h3>

                    <p>
                        ${escapeHtml(
                            business.category || ""
                        )}
                    </p>

                    <p>
                        📍
                        ${escapeHtml(
                            business.address ||
                            "Address unavailable"
                        )}
                    </p>

                    <p>
                        ${offerText}
                    </p>

                </div>

                <span>
                    →
                </span>

            </div>

        </a>
    `;
}


// =========================================================
// FOLLOWING BUSINESSES
// =========================================================

async function loadFollowingBusinesses() {

    sectionTitle.textContent =
        "Following Businesses";


    try {

        const response =
            await fetch(
                "/api/following"
            );


        if (
            response.status === 401
        ) {

            businessList.innerHTML = `
                <div class="business-card">
                    <div>
                        <h3>Login required</h3>

                        <p>
                            Please login to see
                            businesses you follow.
                        </p>
                    </div>
                </div>
            `;

            return;
        }


        if (!response.ok) {

            throw new Error(
                "Failed to load following businesses"
            );
        }


        let businesses =
            await response.json();


        // SEARCH

        if (
            searchText.trim()
        ) {

            const query =
                searchText
                    .trim()
                    .toLowerCase();


            businesses =
                businesses.filter(
                    business => {

                        const name =
                            String(
                                business.name || ""
                            ).toLowerCase();


                        const category =
                            String(
                                business.category || ""
                            ).toLowerCase();


                        const address =
                            String(
                                business.address || ""
                            ).toLowerCase();


                        return (
                            name.includes(query) ||
                            category.includes(query) ||
                            address.includes(query)
                        );
                    }
                );
        }


        // CATEGORY

        if (
            currentCategory !== "all"
        ) {

            businesses =
                businesses.filter(
                    business =>
                        String(
                            business.category || ""
                        )
                        .toLowerCase()
                        .includes(
                            currentCategory.toLowerCase()
                        )
                );
        }


        if (
            !businesses.length
        ) {

            businessList.innerHTML = `
                <div class="business-card">
                    <div>
                        <h3>No businesses found</h3>

                        <p>
                            You are not following any
                            matching businesses.
                        </p>
                    </div>
                </div>
            `;

            return;
        }


        businessList.innerHTML =
            businesses
                .map(
                    business =>
                        createBusinessCard(
                            business
                        )
                )
                .join("");


    } catch (error) {

        console.error(
            "Following error:",
            error
        );


        businessList.innerHTML = `
            <div class="business-card">
                <div>
                    <h3>Unable to load</h3>

                    <p>
                        Please refresh the page.
                    </p>
                </div>
            </div>
        `;
    }
}


// =========================================================
// TAB MANAGEMENT
// =========================================================

function setActiveTab(
    tab
) {

    nearbyTab.classList.remove(
        "active"
    );

    followingTab.classList.remove(
        "active"
    );

    offersTab.classList.remove(
        "active"
    );


    if (
        tab === "nearby"
    ) {

        nearbyTab.classList.add(
            "active"
        );

        sectionTitle.textContent =
            "Businesses";
    }


    if (
        tab === "following"
    ) {

        followingTab.classList.add(
            "active"
        );

        sectionTitle.textContent =
            "Following Businesses";
    }


    if (
        tab === "offers"
    ) {

        offersTab.classList.add(
            "active"
        );

        sectionTitle.textContent =
            "Latest Offers";
    }
}


// =========================================================
// TAB EVENTS
// =========================================================

nearbyTab.addEventListener(
    "click",
    () => {

        currentTab =
            "nearby";

        setActiveTab(
            "nearby"
        );

        renderBusinesses();
    }
);


followingTab.addEventListener(
    "click",
    () => {

        currentTab =
            "following";

        setActiveTab(
            "following"
        );

        renderBusinesses();
    }
);


offersTab.addEventListener(
    "click",
    () => {

        currentTab =
            "offers";

        setActiveTab(
            "offers"
        );

        renderBusinesses();
    }
);


// =========================================================
// SEARCH
// =========================================================

searchInput.addEventListener(
    "input",
    event => {

        searchText =
            event.target.value;

        renderBusinesses();
    }
);


// =========================================================
// CATEGORY FILTERS
// =========================================================

filterButtons.forEach(
    button => {

        button.addEventListener(
            "click",
            () => {

                filterButtons.forEach(
                    item =>
                        item.classList.remove(
                            "active"
                        )
                );


                button.classList.add(
                    "active"
                );


                currentCategory =
                    button.dataset.category;


                renderBusinesses();
            }
        );
    }
);


// =========================================================
// BOTTOM NAVIGATION
// =========================================================

homeNav.addEventListener(
    "click",
    () => {

        window.location.href =
            "/";
    }
);


profileNav.addEventListener(
    "click",
    () => {

        window.location.href =
            "/static/profile.html";
    }
);


// =========================================================
// CATEGORY ICON
// =========================================================

function getCategoryIcon(
    category
) {

    const value =
        String(
            category || ""
        ).toLowerCase();


    if (
        value.includes("cafe")
    ) {

        return "☕";
    }


    if (
        value.includes("restaurant")
    ) {

        return "🍽️";
    }


    if (
        value.includes("shop") ||
        value.includes("store")
    ) {

        return "🛍️";
    }


    return "🏪";
}


// =========================================================
// HTML ESCAPE
// =========================================================

function escapeHtml(
    value
) {

    return String(
        value || ""
    )
    .replace(
        /&/g,
        "&amp;"
    )
    .replace(
        /</g,
        "&lt;"
    )
    .replace(
        />/g,
        "&gt;"
    )
    .replace(
        /"/g,
        "&quot;"
    )
    .replace(
        /'/g,
        "&#039;"
    );
}


// =========================================================
// INITIAL LOAD
// =========================================================

// No GPS.
// Load businesses already saved in database.

loadBusinesses();
